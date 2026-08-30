import tempfile
import unittest
from pathlib import Path

import numpy as np

from app.input_adapter import load_gvhmr_windows, window_starts


def write_params(path: Path, frames: int = 91, fps: float = 30.0) -> None:
    body_pose = np.zeros((frames, 63), dtype=np.float32)
    body_pose[:, 2] = np.linspace(0.0, 0.2, frames, dtype=np.float32)
    transl = np.zeros((frames, 3), dtype=np.float32)
    transl[:, 0] = np.linspace(0.0, 2.0, frames, dtype=np.float32)
    np.savez_compressed(
        path,
        global_orient=np.zeros((frames, 3), dtype=np.float32),
        body_pose=body_pose,
        transl=transl,
        fps=np.asarray(fps, dtype=np.float32),
    )


class InputAdapterTests(unittest.TestCase):
    def test_window_starts_match_training_tail_policy(self) -> None:
        self.assertEqual(window_starts(59), [])
        self.assertEqual(window_starts(60), [0])
        self.assertEqual(window_starts(91), [0, 30, 31])

    def test_gvhmr_smplx_maps_to_motionclip_contract(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "smplx_global_params.npz"
            write_params(source)
            windows, metadata = load_gvhmr_windows(source)
        self.assertEqual(windows.shape, (3, 25, 6, 60))
        self.assertEqual(windows.dtype, np.float32)
        self.assertTrue(np.allclose(windows[:, 24, :3, 0], 0.0))
        self.assertEqual(metadata["window_count"], 3)
        self.assertEqual(metadata["neutral_hand_joints"], [22, 23])

    def test_adapter_rejects_non_30fps_input(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "smplx_global_params.npz"
            write_params(source, frames=60, fps=25.0)
            with self.assertRaisesRegex(ValueError, "30 FPS"):
                load_gvhmr_windows(source)


if __name__ == "__main__":
    unittest.main()
