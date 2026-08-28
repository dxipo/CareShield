import torch

from app.fall_detection.stgcn_extend import STGCNExtend


def test_stgcn_extend_preserves_paper_io_shapes() -> None:
    model = STGCNExtend().eval()
    with torch.inference_mode():
        predicted, logits = model(torch.zeros(1, 1, 100, 17, 2))

    assert predicted.shape == (1, 25, 17, 2)
    assert logits.shape == (1, 2)
