import json, sqlite3, time

class Store:
    def __init__(self,path):
        self.db=sqlite3.connect(path)
        self.db.row_factory=sqlite3.Row
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY,device TEXT,command TEXT,value INTEGER,status TEXT,result TEXT,created REAL,updated REAL);
        CREATE TABLE IF NOT EXISTS schedules(id TEXT PRIMARY KEY,device TEXT,command TEXT,value INTEGER,due REAL,status TEXT,result TEXT);
        CREATE TABLE IF NOT EXISTS samples(id INTEGER PRIMARY KEY,device TEXT,stamp REAL,data TEXT);
        CREATE TABLE IF NOT EXISTS presets(id INTEGER PRIMARY KEY,name TEXT,command TEXT,value INTEGER);
        CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT);
        CREATE TABLE IF NOT EXISTS threads(id TEXT PRIMARY KEY,title TEXT,created REAL);
        CREATE TABLE IF NOT EXISTS messages(id INTEGER PRIMARY KEY,thread TEXT,role TEXT,content TEXT,stamp REAL);
        ''')
        self.db.execute("UPDATE jobs SET status='unknown',result='服务重启，结果未知，不会重发' WHERE status IN ('queued','sent')")
        self.db.execute("UPDATE schedules SET status='unknown',result='服务重启，可能已经发送，不会重发' WHERE status='running'")
        self.db.commit()
    def rows(self,sql,args=()):return [dict(r) for r in self.db.execute(sql,args)]
    def run(self,sql,args=()):
        c=self.db.execute(sql,args);self.db.commit();return c
    def setting(self,key,default=None):
        r=self.rows('SELECT value FROM settings WHERE key=?',(key,));return json.loads(r[0]['value']) if r else default
    def save_setting(self,key,value):self.run('INSERT OR REPLACE INTO settings VALUES(?,?)',(key,json.dumps(value,ensure_ascii=False)))
    def finish(self,id,status,result):self.run('UPDATE jobs SET status=?,result=?,updated=? WHERE id=?',(status,result,time.time(),id))
    def trim(self):
        self.run("DELETE FROM schedules WHERE status NOT IN ('pending','running') AND rowid NOT IN (SELECT rowid FROM schedules ORDER BY due DESC LIMIT 1000)")
        for table,limit,column in [('samples',5000,'id'),('jobs',1000,'created'),('messages',2000,'id')]:
            self.run(f'DELETE FROM {table} WHERE rowid NOT IN (SELECT rowid FROM {table} ORDER BY {column} DESC LIMIT ?)',(limit,))
    def close(self):self.db.close()
