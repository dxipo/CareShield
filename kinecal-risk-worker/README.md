# KINECAL Risk Worker

Independent inference service for the KINECAL-transferred ST-GCN++ model. It
reads only an assessment's `world_skeleton_3d.npz`, converts the GVHMR 21-joint
world skeleton to the exact H36M-17/120-frame training contract, and returns a
three-class cohort result (`NF`, `FHs`, `FHm`).

The worker does not receive EZVIZ credentials or media URLs. The checkpoint is
mounted from ignored `models/` storage and is verified by SHA-256 at startup.
The source license permits academic and non-commercial research only.

This output is a research fall-risk baseline, not a clinical diagnosis. The
single 3 m walk validation subset has limited sensitivity for the high-risk
class, so a low result must not be used to exclude risk.
