import sys
import struct

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python g12.py <number_of_words>")
    num = int(sys.argv[1])
    with open(f"{num}.b12", "wb") as f:
        words = list(range(0, num))
        data = struct.pack(f"<{len(words)}H", *words)
        f.write(data)
