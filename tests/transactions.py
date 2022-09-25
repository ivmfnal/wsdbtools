import sys
from wsdbtools import ConnectionPool, Transaction

conn = ConnectionPool(postgres=" ".join(sys.argv[1:])).connect()

with conn.txn() as txn:
    txn.execute("create table if not exists p(i int primary key)")
    txn.execute("""create table if not exists s(
        i int references p(i), 
        name text, 
        primary key(i, name))
    """)

with conn.txn() as txn:
    #txn.execute("create table if not exists p(i int primary key)")
    for i in range(10):
        txn.execute(f"insert into p(i) values({i})")
        txn.execute(f"insert into s(i, name) values({i}, 'name_{i}')")
    raise RuntimeError("simulated")
    txn.execute("select * from p, s limit 10")
    for tup in txn:
        print(tup)

print("txn committed")

    
