import app.config as config
from app.main import sites_from_file


def test_sites_from_file():
    
    test_csv = config.PATH + r"tests\test_data" + "\\" + "test_monitored_sites.csv"
    sites_data = sites_from_file(test_csv)

    expected_sites_data = [
        ['http://www.reddit.com/', 'Reddit HTTP', ''],
        ['https://github.com/', 'GitHub', 'test1@example.com'],
        ['https://www.theguardian.com/', 'The Guardian', 'test2@example.com'],
    ]
    
    assert sites_data == expected_sites_data
