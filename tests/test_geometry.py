from app.pipeline import point_in_polygon


def test_point_in_polygon_basic() -> None:
    square = [(0, 0), (10, 0), (10, 10), (0, 10)]
    assert point_in_polygon((5, 5), square) is True
    assert point_in_polygon((15, 5), square) is False
