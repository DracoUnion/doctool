import sys
from BookerDownloadTool.whole_site import Base, UrlRecord, get_session_maker
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

def main():
    fname = sys.argv[1]
    print(fname)
    if not fname.endswith('_rec.txt'):
        return
        
    lines = open(fname, encoding='utf8').read().split('\n')
    lines = [l for l in lines if l.strip()]
    proc_cnt = lines.count("-1")
    urls = [l for l in lines if l != "-1"]
    proced_url = urls[:proc_cnt]
    toproc_url = urls[proc_cnt:]
    
    db_fname = fname[:-8] + '.db'
    Session = get_session_maker(db_fname)
    Base.metadata.create_all(Session.kw['bind'])
    
    sess = Session()
    for i, url in enumerate(proced_url):
        print(url)
        sess.add(UrlRecord(url=url, stat=1))
        if i % 1000 == 0: sess.commit()
    for i, url in enumerate(toproc_url):
        print(url)
        sess.add(UrlRecord(url=url, stat=0))
        if i % 1000 == 0: sess.commit()
    
if __name__ == '__main__': main()
    