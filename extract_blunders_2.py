import progressbar
import sys
import math
from datetime import datetime
from database import Db
from stockfish_analysis import get_stockfish_eval
import collections
import random
import copy
import chess

import pprint
pp = pprint.PrettyPrinter()

tree_nodes = 0
class TreeNode:
    def __init__(self, count, openings, fen, next_tree):
        global tree_nodes
        self.count = count
        self.openings = openings
        self.fen = fen
        self.next_tree = next_tree
        self.node_num = tree_nodes
        tree_nodes += 1


def generate_opening_tree(desired_elo=1500, elo_buffer=200, starting_moves="none"):

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

    # Loop through moves of all games
    opening_tree = dict()

    widgets = [
        ' [', progressbar.Timer(), '] ',
        progressbar.Bar(marker='☺'),
        ' (', progressbar.ETA(), ') '
    ]
    bar = progressbar.ProgressBar(
        widgets=widgets, max_value=len(games)).start()

    for index, game in enumerate(games):
        bar.update(index + 1)
        moves = game["moves"].split()
        opening= game["opening"]
        opening_tree = edit_opening_tree(moves, opening, chess.STARTING_FEN, opening_tree)

    bar.finish()
    
    # Close database connection
    DB.close_connection()

    return opening_tree

def edit_opening_tree(moves, opening, fen, tree):
    global tree_nodes
    curr_tree = tree
    curr_board = None
    
    for move in moves:
        
        # Check if move is already in the tree, and get values if so
        if move in curr_tree:
            tn = curr_tree[move]
            count, openings, next_fen, next_tree = tn.count, tn.openings, tn.fen, tn.next_tree
        else:
            count, openings, next_tree = 0, list(), dict()
            if not curr_board:
                curr_board = chess.Board(fen)
            curr_board.push_san(move)
            next_fen = curr_board.fen()

        # Add current openings to list of openings that can lead to this sequence of moves
        if opening not in openings:
            openings.append(opening)

        curr_tree[move] = TreeNode(count + 1, openings, next_fen, next_tree)
        curr_tree = next_tree
        fen = next_fen
    
    return tree


def get_random_path(opening_tree):
    path = []

    next_moves = opening_tree

    while next_moves:
        curr_move, (count, openings, next_moves) = random.choice(list(next_moves.items()))
        path.append(curr_move)

    return " ".join(path)
    

# Finds common blunders based on a list of common positions
tree_index = 0
def find_common_blunders(opening_tree, color="none"):

    # Connect to database
    DB = Db()
    DB.execute("USE chess_analysis")

    blunder_dict = dict()  # Key: FEN positions, Value: (chance of reaching this position, number of following blunders, number of position occurrences, next moves, openings)
    stored_evals = DB.execute("SELECT * from fen_evaluations")
    stored_evals = {fen_eval["fen"]: float(fen_eval["evaluation"]) for fen_eval in stored_evals}  # Key: FEN positions, Value: stockfish evaluation of FEN positions

    blunder_dict = dict()

    widgets = [
        ' [', progressbar.Timer(), '] ',
        progressbar.Bar(marker='☺'),
        ' (', progressbar.ETA(), ') '
    ]
    global bar
    bar = progressbar.ProgressBar(
        widgets=widgets, max_value=tree_nodes).start()
    global tree_index

    search_opening_tree(1, 1, color, opening_tree, blunder_dict, stored_evals, DB)

    bar.finish()

    # Only keep positions with greater than 50% chance of a blunder
    blunder_dict = {k:v for k,v in blunder_dict.items() if v[1]/v[2] > 0.5}

    # Sort blunder dict by probability of blunder descending
    blunder_dict = {k:v for k,v in sorted(blunder_dict.items(), key=lambda x: x[1][1]/x[1][2], reverse=True)}

    # Close database connection
    DB.close_connection()
    return blunder_dict


# Recursively search through opening tree, evaluate FEN positions for blunder potential
def search_opening_tree(depth, pos_prob, color, curr_tree, blunder_dict, stored_evals, DB):
    global bar

    # Get total number of moves in current tree
    curr_move_count = sum(list(tn.count for move, tn in curr_tree.items()))

    # Loop through all moves in current tree
    for move, tn in curr_tree.items():

        bar.update(tn.node_num + 1)

        # Skip move if there are no following moves
        if not tn.next_tree:
            continue

        # Don't consider rare positions
        if tn.count <= max(tree_nodes / 100000, 1):
            continue

        # Get probability of reaching position after current move
        # If playing white, consider probability of all white moves as 100%
        if (color == "white" and depth % 2 == 0) or (color == "black" and depth % 2 == 1) or (color == "none"):
            curr_pos_prob = pos_prob * tn.count / curr_move_count
        else:
            curr_pos_prob = pos_prob

        # Don't calculate blunder probability until move 5
        if depth > 8:

            # Get current board evaluation
            curr_eval, stored_evals = get_fen_eval(tn.fen, stored_evals, DB)
            
            blunder_count = 0

            # Loop through all next moves & check if they are blunders, add to blunder_count if so
            for next_move, next_tn in tn.next_tree.items():
                next_eval, stored_evals = get_fen_eval(next_tn.fen, stored_evals, DB)

                # Check if following position is a blunder
                if (((color == "white" or color == "none") and next_eval - curr_eval >= 0.5 and next_eval >= 0.5) or 
                    ((color == "black" or color == "none") and curr_eval - next_eval >= 0.5 and next_eval <= 0)): 
                    blunder_count += next_tn.count

            # Sort next moves by number of occurrences descending
            next_moves = {next_move: next_tn.count for next_move, next_tn in 
                sorted(tn.next_tree.items(), key=lambda item: item[1].count, reverse=True)}

            # Check if FEN is already in blunder_dict and combine probabilities/counts if so
            if tn.fen in blunder_dict:
                temp_pos_prob, temp_blunder_count, temp_count, temp_next_moves, temp_openings = blunder_dict[tn.fen]
                comb_pos_prob = curr_pos_prob + temp_pos_prob
                comb_blunder_count = blunder_count + temp_blunder_count
                comb_pos_count = tn.count + temp_count
                comb_next_moves = collections.Counter(next_moves) + collections.Counter(temp_next_moves)
                comb_openings = list(set(tn.openings + temp_openings))
                blunder_dict[tn.fen] = (comb_pos_prob, comb_blunder_count, comb_pos_count, comb_next_moves, comb_openings)
            else:
                blunder_dict[tn.fen] = (curr_pos_prob, blunder_count, tn.count, next_moves, tn.openings)

        # Repeat for all next moves
        search_opening_tree(depth+1, curr_pos_prob, color, tn.next_tree, blunder_dict, stored_evals, DB)


# Get FEN evaluation if stored, and if not, add it to DB
def get_fen_eval(fen, stored_evals, DB):
    mate_eval = 5
    if fen in stored_evals:
        eval = stored_evals[fen]
    else:
        print("Calculating eval...")
        eval = get_stockfish_eval(fen)
        eval = round(eval["value"] * 0.01, 2) if eval["type"] == "cp" else math.copysign(mate_eval, eval["value"])
        stored_evals[fen] = eval
        DB.execute("INSERT INTO fen_evaluations (fen, evaluation) VALUES (%s, %s)", (fen, eval))

    return eval, stored_evals

# Generates good openings based on common positions that lead to a player advantage
def generate_good_openings(blunder_dict):
    good_openings = list()
    for fen, (pos_prob, blunder_count, count, next_moves, openings) in blunder_dict.items():
        good_openings.extend(openings)
    
    good_openings = collections.Counter(good_openings)
    return good_openings


# Run program
def run():
    desired_elo = int(input("Desired elo: "))
    elo_buffer = int(input("Elo buffer: "))
    color = input("Color: ").lower()
    starting_moves = input("Starting moves (optional): ").lower()
    print("\n#####################################")

    start_time = datetime.now()

    # Generate opening tree
    print("Generating opening tree...\n")
    opening_tree = generate_opening_tree(desired_elo=desired_elo, elo_buffer=elo_buffer, starting_moves=starting_moves)
    checkpoint1 = datetime.now()

    # Find common blunders
    print("Finding common blunders...\n")
    blunder_dict = find_common_blunders(opening_tree, color)
    checkpoint2 = datetime.now()

    # Generate good openings
    print("Generating good openings...\n")
    good_openings = generate_good_openings(blunder_dict)
    checkpoint3 = datetime.now()

    # Print top 10 blunder positions
    print("Common blunder positions:")
    fen_num = 1
    for fen, (pos_prob, blunder_count, count, next_moves, openings) in list(blunder_dict.items())[:10]:
        print(f"{fen_num}. FEN position: {fen}")
        print(f"Probability of reaching: {pos_prob * 100:.5f}%")

        if color == "white":
            print(f"Probability of gaining a +1 position: {blunder_count / count * 100:.2f}%")
        elif color == "black":
            print(f"Probability of gaining a <0 position: {blunder_count / count * 100:.2f}%")
        elif color  == "none":
            print(f"Probability of gaining a +1 position as white or <0 position as black: {blunder_count / count * 100:.2f}%")

        print("Next moves:")
        for move, count in next_moves.items():
            print(f"{move} - {count}")
        print("Openings: ", end="")
        print(*openings, sep=", ")
        print()
        fen_num += 1

    # Print top 10 good openings
    print("Good openings:")
    opening_num = 1
    for opening in good_openings.most_common(10):
        print(f"{opening_num}. {opening}")
        opening_num += 1
    

    # # Print runtimes
    print("\n")
    print(f"generate_opening_tree runtime: {str(checkpoint1 - start_time)[:-3]}")
    print(f"find_common_blunders runtime: {str(checkpoint2 - checkpoint1)[:-3]}")
    print(f"generate_good_openings runtime: {str(checkpoint3 - checkpoint2)[:-3]}")

run()







# if len(moves) == 0:
    #     return tree

    # curr_move = moves.pop(0)
    # if curr_move in tree:
    #     count, openings, next_moves = tree[curr_move]
    # else:
    #     count, openings, next_moves = 0, list(), dict()

    # if opening not in openings:
    #     openings.append(opening)

    # tree[curr_move] = (count + 1, edit_opening_tree(moves, opening, next_moves))
    # return tree