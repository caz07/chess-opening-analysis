import progressbar
import sys
import math
from datetime import datetime
import chess.pgn
from database import Db
from stockfish_analysis import get_stockfish_eval
import collections

import pprint
pp = pprint.PrettyPrinter()


# Generates dictionaries with the keys as the most common positions reached at the desired elo
def generate_common_positions(desired_elo=1500, elo_buffer=200, starting_moves="none"):

    # Connect to database
    DB = Db()
    DB.execute("USE chess_analysis")

    # Select all games within a certain buffer of the desired elo
    if not starting_moves == "none":
        games = DB.execute("SELECT * FROM opening_moves WHERE elo >= %s AND elo <= %s AND moves LIKE %s ORDER BY moves",
                        (desired_elo - elo_buffer, desired_elo + elo_buffer, starting_moves + "%"))
    else:
        games = DB.execute("SELECT * FROM opening_moves WHERE elo >= %s AND elo <= %s ORDER BY moves",
                       (desired_elo - elo_buffer, desired_elo + elo_buffer))

    # key: common position, value: list containing all played following positions
    pos_dict = dict()
    # key: common position, value: openings that can reach this position
    opening_dict = dict()

    # Create progress bar
    print("Generating common positions...")
    widgets = [
        ' [', progressbar.Timer(), '] ',
        progressbar.Bar(marker='☺'),
        ' (', progressbar.ETA(), ') '
    ]
    bar = progressbar.ProgressBar(
        widgets=widgets, max_value=len(games)).start()

    # Loop through each game
    for index, game in enumerate(games):

        # Update progress bar
        bar.update(index + 1)

        # Get game moves
        moves = game["moves"].split()

        # Get game opening
        opening = game["opening"]

        # Create a board
        # chess_game = chess.pgn.Game()
        board = chess.Board()
        prev_fen, curr_fen = None, None

        # Loop through each move
        for index, move in enumerate(moves):

            # Get FENs of current move and following move
            prev_fen = curr_fen
            board.push_san(move)
            curr_fen = board.fen()

            # After move 3, add the current fen to the list of positions corresponding to the previous fen's key
            # Also add current opening to the list of openings corresponding to the previous fen's key
            min_move_num = 3
            if index > 2*(min_move_num-1)-1:
                pos_dict.setdefault(prev_fen, []).append(curr_fen)

                if prev_fen not in opening_dict or opening not in opening_dict[prev_fen]:
                    opening_dict.setdefault(prev_fen, []).append(opening)

    # Finish progress bar
    bar.finish()
    print("\n")

    # only keep positions that are achieved at least once in every 1000 games and are after a certain move number
    min_occurrences = len(games) * 0.001
    min_move_num = 5
    pos_dict = {k: v for k, v in pos_dict.items() if len(
        v) >= min_occurrences and int(k.split()[-1]) >= min_move_num}

    # Close database connection
    DB.close_connection()
    return pos_dict, opening_dict


# Finds common blunders based on a list of common positions
def find_common_blunders(pos_dict, color="none"):

    # Connect to database
    DB = Db()
    DB.execute("USE chess_analysis")

    blunder_eval_dict = dict()  # Key: common FEN positions that are followed by a blunder,
    # Value: tuple containing current evaluation and average evaluation of following moves
    stored_evals = DB.execute("SELECT * from fen_evaluations")
    stored_evals = {fen_eval["fen"]: float(fen_eval["evaluation"]) for fen_eval in stored_evals}  # Key: FEN positions
    # Value: stockfish evaluation of FEN positions

    # Create progress bar
    print("Finding common blunders...")
    widgets = [
        ' [', progressbar.Timer(), '] ',
        progressbar.Bar(marker='☺'),
        ' (', progressbar.ETA(), ') '
    ]
    bar = progressbar.ProgressBar(
        widgets=widgets, max_value=len(pos_dict)).start()

    # Loop through all common positions and the immediate following moves
    for index, curr_pos in enumerate(pos_dict):

        # Update progress bar
        bar.update(index + 1)

        # Get list of all following positions
        next_pos = pos_dict[curr_pos]
        mate_eval = 5

        # Get stockfish evaluation of current position
        if curr_pos in stored_evals:
            curr_eval = stored_evals[curr_pos]
        else:
            eval = get_stockfish_eval(curr_pos)
            curr_eval = round(
                eval["value"] * 0.01, 2) if eval["type"] == "cp" else math.copysign(mate_eval, eval["value"])
            stored_evals[curr_pos] = curr_eval
            DB.execute("INSERT INTO fen_evaluations (fen, evaluation) VALUES (%s, %s)", (curr_pos, curr_eval))

        # Loop through following positions and sum all of their evaluations
        sum_next_evals = 0
        for new_pos in next_pos:

            if new_pos in stored_evals:
                new_eval = stored_evals[new_pos]
            else:
                eval = get_stockfish_eval(new_pos)
                new_eval = round(eval["value"] * 0.01, 2) if eval["type"] == "cp" else math.copysign(mate_eval, eval["value"])
                stored_evals[new_pos] = new_eval
                DB.execute("INSERT INTO fen_evaluations (fen, evaluation) VALUES (%s, %s)", (new_pos, new_eval))

            sum_next_evals += new_eval

        # Calculate average evaluation of all following positions
        avg_next_eval = round(sum_next_evals / len(next_pos), 2)

        # Store the position if the average next position eval is over 0.5 away from current eval and the next position eval is over +/-1 for the desired color
        eval_buffer = 0.5
        min_next_eval = 1
        if abs(avg_next_eval - curr_eval >= eval_buffer):
            if (color == "none" and abs(avg_next_eval) >= min_next_eval or
                color == "white" and avg_next_eval >= min_next_eval or
                color == "black" and avg_next_eval <= -1 * min_next_eval):
                blunder_eval_dict[curr_pos] = (curr_eval, avg_next_eval)

    # Sort positions in blunder_eval_dict from largest blunders to smallest blunders
    blunder_eval_dict = {k: v for k, v in sorted(
        blunder_eval_dict.items(), key=lambda pos: abs(pos[1][1] - pos[1][0]), reverse=True)}

    # Finish progress bar
    bar.finish()
    print("\n")

    # Close database connection
    DB.close_connection()
    return blunder_eval_dict


# Generates good openings based on common positions that lead to blunders and a player advantage
def generate_good_openings(opening_dict, blunder_eval_dict):
    print("Generating good openings...")
    good_openings = []
    for pos in blunder_eval_dict:
        eval_diff = blunder_eval_dict[pos]
        opening_weight = math.ceil(eval_diff[1] - eval_diff[0])
        for i in range(opening_weight):
            good_openings += opening_dict[pos]

    good_openings = collections.Counter(good_openings)
    good_openings = {k: v for k, v in sorted(
        good_openings.items(), key=lambda opening: opening[1], reverse=True)}

    return good_openings


def run():
    desired_elo = int(input("Desired elo: "))
    elo_buffer = int(input("Elo buffer: "))
    color = input("Color: ").lower()
    starting_moves = input("Starting moves (optional): ").lower()

    start_time = datetime.now()

    pos_dict, opening_dict = generate_common_positions(
        desired_elo=desired_elo, elo_buffer=elo_buffer, starting_moves=starting_moves)
    checkpoint1 = datetime.now()
    for k,v in list(pos_dict.items())[:5]:
        print(k,v)

    blunder_eval_dict = find_common_blunders(pos_dict, color)
    checkpoint2 = datetime.now()

    good_openings = generate_good_openings(opening_dict, blunder_eval_dict)
    checkpoint3 = datetime.now()

    # Print blunder evaluations
    print("\nBlunder eval dict:")
    # pprint.pprint(blunder_eval_dict)

    # Print positions following best positions
    best_pos = next(iter(blunder_eval_dict))
    next_moves = collections.Counter(pos_dict[best_pos])
    next_moves = sorted(next_moves.items(),
                        key=lambda move: move[1], reverse=True)
    print(f"\nMoves after {best_pos}:")
    # pp.pprint(next_moves)

    # Print best openings
    print(
        f"\nGood openings {desired_elo - elo_buffer} to {desired_elo + elo_buffer}:")
    # pprint.pprint(good_openings, sort_dicts=False)

    # Print runtimes
    print("\n")
    print(
        f"generate_common_positions runtime: {str(checkpoint1 - start_time)[:-3]}")
    print(
        f"find_common_blunders runtime: {str(checkpoint2 - checkpoint1)[:-3]}")
    print(
        f"generate_good_openings runtime: {str(checkpoint3 - checkpoint2)[:-3]}")
    

run()
