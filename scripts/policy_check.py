#!/usr/bin/env python3
"""Policy checks on rendered manifests (used by scripts/validate.sh).

Rules:
  * every container image is pinned: tag present, not "latest", and @sha256 digest
  * no privileged containers, no allowPrivilegeEscalation, capabilities drop ALL
  * pods in the application namespace run as non-root and use no hostPath
  * every PersistentVolume has reclaim policy Retain
  * every PV and PVC carries helm.sh/resource-policy=keep and Argo CD Prune=false,Delete=false
"""

import sys

import yaml

APP_NAMESPACE = "mr-do-jellyfin"
KEEP = {"helm.sh/resource-policy": "keep", "argocd.argoproj.io/sync-options": "Prune=false,Delete=false"}


def pod_spec(doc):
    kind = doc.get("kind")
    spec = doc.get("spec", {})
    if kind in ("Deployment", "DaemonSet", "StatefulSet", "Job"):
        return spec.get("template", {}).get("spec")
    if kind == "CronJob":
        return spec.get("jobTemplate", {}).get("spec", {}).get("template", {}).get("spec")
    if kind == "Pod":
        return spec
    return None


def check(docs):
    errors = []
    for doc in docs:
        kind = doc.get("kind")
        meta = doc.get("metadata", {})
        name = f"{kind}/{meta.get('name')}"
        annotations = meta.get("annotations") or {}

        if kind in ("PersistentVolume", "PersistentVolumeClaim"):
            for key, value in KEEP.items():
                if annotations.get(key) != value:
                    errors.append(f"{name}: annotation {key}={value} missing")
        if kind == "PersistentVolume" and doc["spec"].get("persistentVolumeReclaimPolicy") != "Retain":
            errors.append(f"{name}: persistentVolumeReclaimPolicy must be Retain")

        spec = pod_spec(doc)
        if not spec:
            continue
        namespace = meta.get("namespace", APP_NAMESPACE)
        pod_sc = spec.get("securityContext") or {}
        for container in spec.get("initContainers", []) + spec.get("containers", []):
            cname = f"{name}/{container['name']}"
            image = container.get("image", "")
            ref = image.split("@")[0]
            tag = ref.rsplit(":", 1)[1] if ":" in ref.rsplit("/", 1)[-1] else ""
            if "@sha256:" not in image:
                errors.append(f"{cname}: image {image} has no @sha256 digest")
            if not tag or tag == "latest":
                errors.append(f"{cname}: image {image} must use a fixed tag (not latest)")
            sc = container.get("securityContext") or {}
            if sc.get("privileged"):
                errors.append(f"{cname}: privileged container")
            if sc.get("allowPrivilegeEscalation", True):
                errors.append(f"{cname}: allowPrivilegeEscalation must be false")
            if "ALL" not in ((sc.get("capabilities") or {}).get("drop") or []):
                errors.append(f"{cname}: capabilities must drop ALL")
            if namespace == APP_NAMESPACE and not (sc.get("runAsNonRoot") or pod_sc.get("runAsNonRoot")):
                errors.append(f"{cname}: runAsNonRoot must be true")
        if namespace == APP_NAMESPACE:
            for volume in spec.get("volumes", []):
                if "hostPath" in volume:
                    errors.append(f"{name}: hostPath volume {volume['name']} not allowed in {APP_NAMESPACE}")
    return errors


def main(paths):
    docs = []
    for path in paths:
        with open(path, encoding="utf-8") as handle:
            docs.extend(d for d in yaml.safe_load_all(handle) if d)
    errors = check(docs)
    for error in errors:
        print(f"    {error}")
    print(f"    {len(docs)} objects checked, {len(errors)} violation(s)")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
