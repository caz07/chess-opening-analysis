from stockfish import Stockfish

stockfish = Stockfish(r"C:\\Program Files\\stockfish_14_win_x64_avx2\\stockfish_14_x64_avx2.exe", parameters={
    "Write Debug Log": "false",
    "Contempt": 0,
    "Min Split Depth": 0,
    "Threads": 2,
    "Ponder": "false",
    "Hash": 16,
    "MultiPV": 1,
    "Skill Level": 20,
    "Move Overhead": 30,
    "Minimum Thinking Time": 20,
    "Slow Mover": 80,
    "UCI_Chess960": "false",
})
stockfish.set_depth(20)


def get_stockfish_eval(fen):
    stockfish.set_fen_position(fen)
    eval = stockfish.get_evaluation()
    return eval
