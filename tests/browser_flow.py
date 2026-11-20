"""Optional real Chromium integration test: pip install playwright; playwright install chromium."""
import os, tempfile, threading
from pathlib import Path
from playwright.sync_api import sync_playwright, expect
from server import make_server


def run():
    with tempfile.TemporaryDirectory() as temp:
        server=make_server(Path(temp)/'browser.sqlite3',port=0); threading.Thread(target=server.serve_forever,daemon=True).start(); base=f'http://127.0.0.1:{server.server_port}'
        try:
            with sync_playwright() as p:
                args={'headless':True,'args':['--no-sandbox']}; exe=os.environ.get('CHROMIUM_EXECUTABLE');
                if exe: args['executable_path']=exe
                browser=p.chromium.launch(**args); ctx=browser.new_context(viewport={'width':1440,'height':1000},accept_downloads=True); errors=[]
                def page(user):
                    pg=ctx.new_page(); pg.on('pageerror',lambda e:errors.append(str(e))); pg.goto(base+'/?user='+user); expect(pg.locator('#connection')).to_contain_text('Live connected',timeout=10000); return pg
                a=page('am23456'); b=page('sc12345'); c=page('dl34567'); d=page('mb45678')
                mock=browser.new_page(viewport={'width':1150,'height':950}); mock.on('pageerror',lambda e:errors.append(str(e))); mock.goto(base+'/mock'); expect(mock.locator('#mockTitle')).to_have_value('Trade validation failure'); mock.locator('#publishBtn').click(); expect(mock.locator('#mockResult')).to_contain_text('Published'); print('PASS: mock alert published through simulator UI',flush=True)
                for pg in [a,b]: expect(pg.locator('#popupHost .popup')).to_contain_text('Trade validation failure',timeout=10000)
                expect(c.locator('#popupHost .popup')).to_have_count(0); expect(d.locator('#popupHost .popup')).to_have_count(0); print('PASS: both selected subscribers automatically receive popups; others do not',flush=True)
                shot=os.environ.get('PULSE_SCREENSHOT_DIR');
                if shot: Path(shot).mkdir(parents=True,exist_ok=True); a.screenshot(path=str(Path(shot)/'01-alert-popup.png')); mock.screenshot(path=str(Path(shot)/'02-simulator.png'))
                a.locator('#popupHost').get_by_role('button',name='Take ownership').click(); expect(b.locator('#popupHost .popup')).to_contain_text('Owner: Alex Morgan',timeout=10000); expect(b.locator('#popupHost').get_by_role('button',name='Take ownership')).to_have_count(0); print('PASS: ownership updates other user and removes claim action',flush=True)
                a.locator('#popupHost').get_by_role('button',name='Open discussion').click(); expect(a.locator('#detailHost h2')).to_have_text('Trade validation failure'); b.locator('#popupHost').get_by_role('button',name='Open discussion').click(); expect(b.locator('#detailHost h2')).to_have_text('Trade validation failure')
                a.locator('#messageInput').fill('Investigating now.'); a.locator('#sendBtn').click(); expect(b.locator('#chatContent')).to_contain_text('Investigating now.',timeout=10000); print('PASS: real-time chat',flush=True)
                a.locator('#messageInput').fill('@dl'); expect(a.locator('#mentionMenu')).to_be_visible(); a.locator('#mentionMenu').get_by_role('button',name='Daniel Lee',exact=False).click(); a.locator('#messageInput').press('End'); a.locator('#messageInput').press_sequentially('Please check logs.'); a.locator('#sendBtn').click(); expect(c.locator('#popupHost')).to_contain_text('You were mentioned',timeout=10000); expect(c.locator('#popupHost')).to_contain_text('Please check logs.'); c.locator('#popupHost').get_by_role('button',name='Open discussion').click(); expect(c.locator('#chatContent')).to_contain_text('Investigating now.'); print('PASS: @SOEID autocomplete, mention popup and access to earlier messages',flush=True)
                a.locator('#peopleBtn').click(); a.locator('#peopleSearch').fill('mb45678'); a.get_by_role('checkbox',name='Invite Michael Brown').check(); a.locator('#inviteConfirm').click(); expect(d.locator('#popupHost')).to_contain_text('You were invited',timeout=10000); d.locator('#popupHost').get_by_role('button',name='Dismiss').click(); expect(d.locator('#popupHost .popup')).to_have_count(0); expect(a.locator('#detailHost')).to_contain_text('In progress'); print('PASS: invite plus local dismissal without altering shared alert',flush=True)
                raw=b'Subject: Support update\r\nFrom: support@example.com\r\nTo: demo@example.com\r\n\r\nThe worker was restarted.\r\n'; a.locator('#fileInput').set_input_files({'name':'support.eml','mimeType':'message/rfc822','buffer':raw}); expect(b.locator('#chatContent')).to_contain_text('support.eml',timeout=10000); b.locator('#chatContent').get_by_text('Email preview').click(); expect(b.locator('#chatContent')).to_contain_text('The worker was restarted.');
                with b.expect_download() as dl: b.locator('#chatContent').get_by_role('link',name='Download attachment').click()
                assert Path(dl.value.path()).read_bytes()==raw
                print('PASS: email upload, live preview and byte-identical download',flush=True)
                if shot: a.screenshot(path=str(Path(shot)/'03-discussion.png'))
                a.locator('#detailHost').get_by_role('button',name='Resolve',exact=True).click(); a.locator('#resolutionInput').fill('Restarted worker and verified order submissions.'); a.locator('#confirmResolve').click(); expect(b.locator('#detailHost .resolution-note')).to_contain_text('Restarted worker',timeout=10000); expect(c.locator('#detailHost')).to_contain_text('Resolved'); print('PASS: resolution synchronizes across three workspaces',flush=True)
                a.get_by_role('button',name='History',exact=False).click(); expect(a.locator('#alertList')).to_contain_text('Trade validation failure'); a.locator('#detailHost').get_by_role('button',name='Activity',exact=False).click(); expect(a.locator('#chatContent')).to_contain_text('Resolved'); expect(a.locator('#chatContent')).to_contain_text('Invited'); a.reload(); expect(a.locator('#alertList')).to_contain_text('Trade validation failure'); expect(a.locator('#detailHost')).to_contain_text('Resolved'); expect(a.locator('#chatContent')).to_contain_text('support.eml'); print('PASS: history, audit log and persistence after reload',flush=True)
                if shot: a.screenshot(path=str(Path(shot)/'04-resolved.png'))
                assert not errors,errors; print('PASS: zero browser JavaScript exceptions',flush=True); browser.close()
        finally: server.stopping.set(); server.store.wake(); server.shutdown(); server.server_close()

if __name__=='__main__': run()
