from scripts.audit_public_indices import quote_summary,history_summary,chain_summary


def test_index_audit_excludes_unapproved_fields():
    q=dict(instrument=dict(symbol='SPX'),last='6000',secret='never',accountId='never')
    assert 'never' not in str(quote_summary({'quotes':[q]}))
    assert history_summary({'regularMarket':{'bars':[]},'secret':'never'})['count']==0
    c=chain_summary({'calls':[dict(q,optionDetails=dict(strikePrice='6000'))],'puts':[],'secret':'never'})
    assert c['calls']['sample'][0]['strike']=='6000'
    assert 'never' not in str(c)
