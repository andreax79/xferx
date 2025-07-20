import sys

from xferx.commons import IMAGE
from xferx.device.block_18bit import from_18bit_words_to_bytes

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python g18.py <number_of_words>")
    num = int(sys.argv[1])
    with open(f"{num}.b18", "wb") as f:
        words = list(range(0, num))
        data = from_18bit_words_to_bytes(words, IMAGE)
        f.write(data)
