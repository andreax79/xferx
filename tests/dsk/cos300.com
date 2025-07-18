INITIALIZE/COS300 cos300.tu56
MOUNT/COS300 tu: cos300.tu56
COPY data/1.txt tu:A1.A
COPY data/2.txt tu:A2.A
COPY data/5.txt tu:A5.A
COPY data/10.txt tu:A10.A
COPY data/20.txt tu:A20.A
COPY data/50.txt tu:A50.A
COPY data/100.txt tu:A100.A
COPY data/200.txt tu:A200.A
COPY data/500.txt tu:A500.A
COPY data/dibol.s tu:DIBOL.S
DIR tu:
