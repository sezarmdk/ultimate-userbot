import asyncio
from core.cleanup import ResponseCleanup

class FakeClient:
    def __init__(self, fail=False):
        self.deleted=[]; self.fail=fail
    async def delete_messages(self, chat_id, message_id):
        if self.fail: raise RuntimeError('temporary delete failure')
        self.deleted.append((chat_id,message_id))

async def main():
    # Per-chat independence and latest-two behavior.
    c=FakeClient(); clean=ResponseCleanup(c, limit=2)
    await clean.add(1,101); await clean.add(1,102); await clean.add(1,103)
    assert c.deleted == [(1,101)]
    assert list(clean.history[1]) == [102,103]
    await clean.add(2,201); await clean.add(2,202)
    assert list(clean.history[2]) == [201,202]

    # Failed delete must preserve cleanup state for a future retry.
    bad=FakeClient(fail=True); retry=ResponseCleanup(bad, limit=2)
    await retry.add(9,1); await retry.add(9,2); await retry.add(9,3)
    assert list(retry.history[9]) == [1,2,3]
    bad.fail=False
    await retry.add(9,4)
    assert list(retry.history[9]) == [3,4]
    assert bad.deleted == [(9,1),(9,2)]
    print('PHASE 13 RESPONSE CLEANUP TEST: PASS')
    print('PHASE 13 PER-CHAT ISOLATION TEST: PASS')
    print('PHASE 13 RETRY-SAFETY TEST: PASS')

asyncio.run(main())
