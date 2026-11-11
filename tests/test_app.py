import io
import cv2
import numpy as np
import pytest
from starlette.testclient import TestClient
from diff_game.app import app


@pytest.fixture
def client():
    return TestClient(app)


def test_get_root_serves_html(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "找茬" in response.text or "Difference" in response.text


def test_api_compare_invalid_file(client):
    response = client.post(
        "/api/compare",
        files={"file": ("test.txt", b"not an image", "text/plain")},
        data={"split_mode": "auto"},
    )
    assert response.status_code == 400


def test_api_compare_valid_image(client):
    # Create sample image 400x200
    img = np.ones((200, 400, 3), dtype=np.uint8) * 100
    cv2.circle(img, (300, 100), 10, (255, 255, 255), -1)
    success, encoded_img = cv2.imencode(".png", img)
    assert success

    file_bytes = io.BytesIO(encoded_img.tobytes())
    response = client.post(
        "/api/compare",
        files={"file": ("sample.png", file_bytes, "image/png")},
        data={
            "split_mode": "auto",
            "diff_threshold": 25,
            "min_area": 30,
            "blur_radius": 3,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["difference_count"] == 1
    assert data["split_mode"] == "horizontal"
    assert "annotated_image_base64" in data
    assert data["annotated_image_base64"].startswith("data:image/png;base64,")
