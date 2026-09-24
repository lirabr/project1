import json
from datetime import UTC, datetime, timedelta

import pytest

from desk import io_utils
from desk.cli import build_parser
from desk.portfolio import PortfolioTarget


def run(*args):
    parsed = build_parser().parse_args(list(args))
    parsed.func(parsed)


def test_cli_plan_approval_fill_and_stats(tmp_path, capsys):
    now = datetime.now(UTC)
    marks = tmp_path / "marks.json"
    marks.write_text(json.dumps({"SPY": {"price": 100., "as_of": now.isoformat()}}))
    target = PortfolioTarget({"SPY": .01}, (now - timedelta(seconds=2)).isoformat(),
                             (now - timedelta(seconds=1)).isoformat(), "model", "data", "cfg")
    path = tmp_path / "target.json"
    path.write_text(json.dumps(target.to_dict()))
    run("paper", "session", "--session", "test", "--marks", str(marks))
    capsys.readouterr()
    run("paper", "plan", "--target", str(path), "--marks", str(marks))
    plan = json.loads(capsys.readouterr().out)
    order_id = plan["orders"][0]["order_id"]
    from desk.memory import connect

    conn = connect()
    assert conn.execute("SELECT COUNT(*) FROM desk_orders").fetchone()[0] == 0
    with pytest.raises(ValueError):
        run("paper", "approve", "--target", str(path), "--marks", str(marks), "--order-id", order_id, "--session", "test")
    run("paper", "approve", "--target", str(path), "--marks", str(marks), "--order-id", order_id,
        "--session", "test", "--reviewer", "operator")
    capsys.readouterr()
    run("paper", "fill", "--order-id", order_id, "--fill-id", "cli-fill", "--quantity", "10", "--price", "100", "--marks", str(marks))
    assert json.loads(capsys.readouterr().out)["status"] == "FILLED"
    run("paper", "book", "--marks", str(marks), "--session", "test")
    book = json.loads(capsys.readouterr().out)
    assert book["equity"] == 100000 and book["cash"] == 99000
    assert book["statistics"]["orders"]["buy_FILLED"] == 1
    assert not (io_utils.ARTIFACT_DIR / "audit.jsonl").exists()
    conn.close()
