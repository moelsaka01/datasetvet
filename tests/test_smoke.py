from datasetdoctor import __version__
from datasetdoctor.cli import main


def test_version_string():
    assert __version__ == "0.0.0"


def test_cli_says_not_implemented(capsys):
    assert main([]) == 2
    assert "nothing is implemented yet" in capsys.readouterr().err
