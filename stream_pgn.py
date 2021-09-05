import urllib.request
import bz2
import pprint

import sys

filename = 'temp.file'


def decompression(qin,                 # Iterable supplying input bytes data
                  qout):               # Pipe to next process - needs bytes data
    decomp = bz2.BZ2Decompressor()     # Create a decompressor
    for chunk in qin:                  # Loop obtaining data from source iterable
        dc = decomp.decompress(chunk)  # Do the decompression
        qout.write(dc)
        while decomp.eof:
            remaining_data = decomp.unused_data
            decomp = bz2.BZ2Decompressor()
            dc = decomp.decompress(remaining_data)
            qout.write(dc)
        # qout.put(dc)                   # Pass the decompressed chunk to the next process


req = urllib.request.urlopen(
    'https://database.lichess.org/standard/lichess_db_standard_rated_2013-01.pgn.bz2')
it = iter(lambda: req.read(16384), b'')

decompression(it, sys.stdout.buffer)
