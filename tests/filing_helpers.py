"""Explicit consent in tests that exercise the complete filing workflow."""
def classify(engine, ids, destination, document_ids=None):
    plan=engine.prepare_classify(ids,destination,document_ids)
    return engine.confirm_operation(plan['id'],True)

def undo(engine,id,token):
    plan=engine.prepare_undo(id,token)
    engine.confirm_operation(plan['id'],True)
    return engine.store.get('document',id)

def post_classify(client,headers,body):
    plan=client.post('/api/classify/prepare',headers=headers,json=body)
    if plan.status_code!=200:return plan
    return client.post('/api/file-operations/'+plan.json()['id']+'/confirm',headers=headers,json={'confirm':True})
