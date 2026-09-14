
class EditService:
    def __init__(self, db): self.db=db

    async def initialize(self):
        assert self.db.conn
        await self.db.conn.executescript("""
        CREATE TABLE IF NOT EXISTS edit_history (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          chat_id INTEGER NOT NULL, message_id INTEGER NOT NULL,
          user_id INTEGER, username TEXT, original_text TEXT,
          new_text TEXT, original_time TEXT, edit_time TEXT,
          edit_count INTEGER NOT NULL DEFAULT 1,
          UNIQUE(chat_id,message_id,edit_count)
        );
        CREATE INDEX IF NOT EXISTS idx_edit_chat_msg ON edit_history(chat_id,message_id);
        """)
        await self.db.conn.commit()

    async def record(self, chat_id,message_id,user_id,username,original,new,original_time,edit_time):
        assert self.db.conn
        async with self.db.conn.execute(
            "SELECT COALESCE(MAX(edit_count),0) FROM edit_history WHERE chat_id=? AND message_id=?",
            (chat_id,message_id)) as c: row=await c.fetchone()
        count=row[0]+1
        await self.db.conn.execute("""INSERT INTO edit_history
        (chat_id,message_id,user_id,username,original_text,new_text,original_time,edit_time,edit_count)
        VALUES(?,?,?,?,?,?,?,?,?)""",(chat_id,message_id,user_id,username,original,new,original_time,edit_time,count))
        await self.db.conn.commit()
        return count
