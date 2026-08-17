CREATE/ALLOCATE:0 os32mt.tap
INITIALIZE/os32mt os32mt.tap
MOUNT/os32mt mag1: os32mt.tap
COPY /type:co data/1.txt mag1:d1.txt/0
COPY /type:co data/2.txt mag1:d2.txt/0
COPY /type:co data/5.txt mag1:d5.txt/0
COPY /ascii data/10.txt mag1:d10.txt/10
COPY /ascii data/20.txt mag1:d20.txt/10
COPY /ascii data/50.txt mag1:d50.txt/10
COPY /ascii data/100.txt mag1:d100.txt/20
COPY /ascii data/200.txt mag1:d200.txt/20
COPY /ascii data/500.txt mag1:d500.txt/20
COPY /ascii data/1000.txt mag1:d1000.txt/30
COPY /ascii data/2000.txt mag1:d2000.txt/30
