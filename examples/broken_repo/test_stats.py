from stats import average


def test_empty():
    assert average([]) == 0.0

def test_mean():
    assert average([2.0, 4.0]) == 3.0
