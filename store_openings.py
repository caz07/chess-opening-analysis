import sys
from datetime import datetime
import chess
from database import Db

import pprint

def store_opening_moves(pgn, pgn_id=-1):
    # Connect to database
    DB = Db()
    DB.execute("USE chess_analysis")

    # Read through all chess games in the pgn
    while True:
        game = chess.pgn.read_game(pgn)

        # Exit when there are no more games
        if game == None:
            break

        # Get average elo of players
        try:
            elo = (int(game.headers["WhiteElo"]) +
                   int(game.headers["BlackElo"])) / 2
        except ValueError:
            continue

        # Play through each move and store the first 20 as a string
        board = game.board()
        game_moves = list()
        for index, move in enumerate(game.mainline_moves()):
            if index >= 40:
                continue
            game_moves.append(board.san(move))
            board.push(move)
        game_moves = " ".join(game_moves)

        # Get game opening and time control
        opening = game.headers["Opening"]
        time_control = game.headers["TimeControl"]

        # Store first 20 moves of each game in database
        DB.execute("INSERT INTO opening_moves (moves, elo, opening, time_control, pgn_id) VALUES (%s, %s, %s, %s, %s)",
                   (game_moves, elo, opening, time_control, pgn_id))

    # Close database connection
    DB.close_connection()


def run():
    pgn = sys.stdin

    start_time = datetime.now()
    store_opening_moves(pgn)
    end_time = datetime.now()

    print(
        f"store_opening_moves runtime: {str(end_time - start_time)[:-3]}")


run()
