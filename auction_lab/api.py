"""Local JSON API. Standard library only; no real broker or exchange connection."""
import argparse
from dataclasses import fields
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import secrets
from urllib.parse import parse_qs, urlparse

from .data import load_data, synthetic_data
from .engine import Config, Game
from .report import clean_json


def serve(port=8000, data_path=None):
    games = {}
    fixed_data = load_data(data_path) if data_path else None

    class Handler(BaseHTTPRequestHandler):
        def reply(self, status, payload):
            encoded = json.dumps(clean_json(payload), allow_nan=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def body(self):
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 <= length <= 1_000_000:
                raise ValueError("Request body must be at most 1 MB")
            data = json.loads(self.rfile.read(length) or b"{}")
            if not isinstance(data, dict):
                raise ValueError("JSON body must be an object")
            return data

        def route(self, method):
            parsed = urlparse(self.path)
            parts = [x for x in parsed.path.split("/") if x]
            try:
                if method == "GET" and parts == ["health"]:
                    return self.reply(200, {"status": "ok", "mode": "local simulation"})
                if method == "POST" and parts == ["games"]:
                    if len(games) >= 20:
                        raise ValueError("At most 20 local games; delete an old game first")
                    body = self.body()
                    allowed = {f.name for f in fields(Config)}
                    if set(body) - allowed:
                        raise ValueError(f"Unknown configuration fields: {set(body) - allowed}")
                    config = Config(**body)
                    if config.days > 500 or config.warmup > 1000:
                        raise ValueError("API limits: at most 500 evaluation and 1000 warm-up days")
                    data = fixed_data if fixed_data is not None else synthetic_data(max(80, config.warmup + config.days), config.seed)
                    label = "user-supplied historical data" if fixed_data is not None else "SYNTHETIC demonstration"
                    game = Game(data, config, human=True, data_label=label)
                    game_id = secrets.token_hex(8)
                    games[game_id] = game
                    return self.reply(201, {"game_id": game_id, "state": game.observation()})
                if len(parts) >= 2 and parts[0] == "games":
                    game = games.get(parts[1])
                    if game is None:
                        return self.reply(404, {"error": "Unknown game"})
                    if len(parts) == 2 and method == "DELETE":
                        del games[parts[1]]
                        return self.reply(200, {"deleted": True})
                    if len(parts) == 2 and method == "GET":
                        return self.reply(200, game.observation())
                    if len(parts) == 3 and parts[2] == "history" and method == "GET":
                        query = parse_qs(parsed.query)
                        limit = int(query.get("limit", ["126"])[0])
                        if not 1 <= limit <= 1000:
                            raise ValueError("history limit must be between 1 and 1000 dates")
                        return self.reply(200, {"history": game.history(query.get("symbol", [None])[0], limit)})
                    if len(parts) == 3 and parts[2] == "step" and method == "POST":
                        body = self.body()
                        if set(body) - {"quotes"}:
                            raise ValueError("step accepts only a quotes field")
                        result = game.step(body.get("quotes", {}))
                        return self.reply(200, {"result": result, "next_state": game.observation()})
                    if len(parts) == 3 and parts[2] == "quotes" and method == "GET":
                        query = parse_qs(parsed.query)
                        limit = int(query.get("limit", ["126"])[0])
                        if not 1 <= limit <= 1000:
                            raise ValueError("quote history limit must be between 1 and 1000 dates")
                        return self.reply(200, {"completed_quotes": game.completed_quotes(limit, query.get("symbol", [None])[0])})
                    if len(parts) == 3 and parts[2] == "results" and method == "GET":
                        return self.reply(200, {"done": game.done, "days_completed": game.index,
                                                "leaderboard": game.leaderboard().to_dict("records"),
                                                "daily_pnl": game.daily})
                return self.reply(404, {"error": "Unknown endpoint"})
            except (ValueError, TypeError, KeyError, OverflowError) as exc:
                return self.reply(400, {"error": str(exc)})

        def do_GET(self):
            self.route("GET")

        def do_POST(self):
            self.route("POST")

        def do_DELETE(self):
            self.route("DELETE")

    server = HTTPServer(("127.0.0.1", port), Handler)
    print(f"Auction API: http://127.0.0.1:{server.server_port} (local research use)", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--data")
    args = parser.parse_args()
    serve(args.port, args.data)

