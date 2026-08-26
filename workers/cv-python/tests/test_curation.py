import pytest
import cv2
import numpy as np
from pathlib import Path
from activities.curation import laplacian_blur_score

@pytest.fixture(scope="session", autouse=True)
def create_fixtures():
    fixtures = Path("tests/fixtures")
    fixtures.mkdir(parents=True, exist_ok=True)
    
    # Create sharp_tile.png
    sharp = np.zeros((256, 256), dtype=np.uint8)
    # add some sharp edges
    cv2.rectangle(sharp, (50, 50), (200, 200), 255, -1)
    cv2.line(sharp, (10, 10), (240, 240), 128, 5)
    cv2.imwrite(str(fixtures / "sharp_tile.png"), sharp)
    
    # Create sample_segment.mp4
    out = cv2.VideoWriter(
        str(fixtures / "sample_segment.mp4"),
        cv2.VideoWriter_fourcc(*"mp4v"),
        30.0, (640, 480)
    )
    for i in range(60):
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        cv2.putText(frame, f"Frame {i}", (100, 100), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2)
        out.write(frame)
    out.release()

def test_laplacian_blur_rejects_blurred_frame():
    sharp = cv2.imread("tests/fixtures/sharp_tile.png", cv2.IMREAD_GRAYSCALE)
    blurred = cv2.GaussianBlur(sharp, (15, 15), 0)
    assert laplacian_blur_score(sharp) > laplacian_blur_score(blurred)

# We would need to mock the object_store to fully test short circuiting
# For this scaffold, we skip full e2e without a minio instance
