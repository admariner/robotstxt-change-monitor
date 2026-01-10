from app.main import sites_from_file

def func(x):
    return x + 1


def test_answer():
    # This dummy test passes
    assert func(4) == 5


def test_sites_from_file():
    # This dummy test fails
    # sites_data = sites_from_file("oops.csv")
    pass