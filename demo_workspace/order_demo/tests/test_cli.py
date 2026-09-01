from cli import main


def test_cli_keeps_existing_item_and_coupon_interface(capsys) -> None:
    exit_code = main(["BOOK:1", "--coupon", "SAVE10"])

    assert exit_code == 0
    assert capsys.readouterr().out.strip() == "items=1 total=97.20"
