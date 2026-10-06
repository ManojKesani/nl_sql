from nlsql.db.executor import run_query, QueryRejected
from nlsql.db.introspect import profile_db, render_schema_card, save_profile

print(run_query("longlist.db", "SELECT count(*) FROM books").to_dict())

for bad in ["DROP TABLE books", "SELECT 1; SELECT 2", "PRAGMA table_info(books)",
            "WITH x AS (SELECT 1) DELETE FROM books"]:
    try:
        run_query("longlist.db", bad); print("NOT REJECTED:", bad)
    except QueryRejected as e:
        print("rejected:", bad, "->", e)

# legit semicolon inside a string literal now works:
print(run_query("longlist.db", "SELECT 'a;b' AS x").rows)

# timeout: should raise QueryTimeout quickly
from nlsql.db.executor import QueryTimeout
try:
    run_query("longlist.db",
              "WITH RECURSIVE c(x) AS (SELECT 1 UNION ALL SELECT x+1 FROM c) SELECT count(*) FROM c",
              timeout_s=1)
except QueryTimeout as e:
    print("timeout ok:", e)

p = profile_db("longlist.db")
save_profile(p, "data/longlist/profile.json")
print(render_schema_card(p))