"""Optional real-browser test for V2 independent windows and the standalone listener.
Run after installing Playwright and Chromium. Does not require a real Finsemble runtime.
"""
import os, tempfile, threading
from pathlib import Path
from playwright.sync_api import sync_playwright, expect
from server import make_server


def run():
    with tempfile.TemporaryDirectory() as tmp:
        server=make_server(Path(tmp)/'window.sqlite3',port=0)
        threading.Thread(target=server.serve_forever,daemon=True).start()
        base=f'http://127.0.0.1:{server.server_port}'
        try:
            with sync_playwright() as p:
                options={'headless':True,'args':['--no-sandbox']}
                if os.getenv('CHROMIUM_EXECUTABLE'): options['executable_path']=os.environ['CHROMIUM_EXECUTABLE']
                browser=p.chromium.launch(**options)
                ctx=browser.new_context(accept_downloads=True)
                errors=[]
                ctx.on('page',lambda page:page.on('pageerror',lambda e:errors.append(str(e))))
                a=ctx.new_page(); a.goto(base+'/?user=am23456'); expect(a.locator('#connection')).to_contain_text('Live connected')
                a.locator('#popupMode').click(); expect(a.locator('#popupMode')).to_contain_text('Window')
                b=ctx.new_page(); b.goto(base+'/?user=sc12345'); expect(b.locator('#connection')).to_contain_text('Live connected')
                b.locator('#popupMode').click(); expect(b.locator('#popupMode')).to_contain_text('Window')
                # Daniel has no workspace running. Only his background listener remains open.
                listener=ctx.new_page(); listener.goto(base+'/listener.html?user=dl34567'); expect(listener.locator('#listenerStatus')).to_contain_text('Live connected')
                mock=ctx.new_page(); mock.goto(base+'/mock'); expect(mock.locator('#mockTitle')).to_have_value('Trade validation failure')
                with a.expect_popup(timeout=15000) as ap, b.expect_popup(timeout=15000) as bp:
                    mock.locator('#publishBtn').click()
                x,y=ap.value,bp.value
                for page in (x,y):
                    expect(page.locator('#detailHost h2')).to_have_text('Trade validation failure'); expect(page.locator('#connection')).to_contain_text('Live connected')
                print('PASS: two separate Web alert windows opened automatically',flush=True)
                x.locator('#detailHost').get_by_role('button',name='Take ownership').click(); expect(y.locator('#detailHost')).to_contain_text('Alex Morgan'); expect(y.locator('#detailHost').get_by_role('button',name='Take ownership')).to_have_count(0)
                x.locator('#messageInput').fill('Investigating now'); x.locator('#sendBtn').click(); expect(y.locator('#chatContent')).to_contain_text('Investigating now')
                x.locator('#messageInput').fill('@dl34567 Please check logs.')
                with listener.expect_popup(timeout=15000) as dp: x.locator('#sendBtn').click()
                z=dp.value; expect(z.locator('#popupReason')).to_have_text('You were mentioned'); expect(z.locator('#chatContent')).to_contain_text('Please check logs.')
                print('PASS: claim sync, chat and background-only mention window',flush=True)
                # Send another mention, ensuring the existing window is reused.
                x.locator('#messageInput').fill('@dl34567 Another update.'); x.locator('#sendBtn').click(); expect(z.locator('#chatContent')).to_contain_text('Another update.')
                assert len([pg for pg in ctx.pages if '/alert-popup.html?' in pg.url and 'user=dl34567' in pg.url])==1
                x.locator('#peopleBtn').click(); x.locator('#peopleSearch').fill('mb45678'); x.get_by_role('checkbox',name='Invite Michael Brown').check(); x.locator('#inviteConfirm').click(); expect(x.locator('#chatContent')).to_be_visible()
                raw=b'Subject: Support update\r\nFrom: support@example.com\r\n\r\nThe service was restored.\r\n'
                x.locator('#fileInput').set_input_files({'name':'support.eml','mimeType':'message/rfc822','buffer':raw}); expect(y.locator('#chatContent')).to_contain_text('support.eml'); y.locator('#chatContent').get_by_text('Email preview').click(); expect(y.locator('#chatContent')).to_contain_text('The service was restored.')
                with y.expect_download() as dl: y.locator('#chatContent').get_by_role('link',name='Download attachment').click()
                assert Path(dl.value.path()).read_bytes()==raw
                shot=os.getenv('PULSE_SCREENSHOT_DIR')
                if shot: Path(shot).mkdir(parents=True,exist_ok=True); x.screenshot(path=str(Path(shot)/'05-web-alert-window.png'))
                x.locator('#detailHost').get_by_role('button',name='Resolve',exact=True).click(); x.locator('#resolutionInput').fill('Service restored and verified'); x.locator('#confirmResolve').click(); expect(y.locator('#detailHost')).to_contain_text('Service restored and verified'); expect(z.locator('#detailHost')).to_contain_text('Resolved')
                print('PASS: reuse, invite, attachment and resolved status in standalone windows',flush=True)
                y.locator('#closeWindow').click(); expect(b.locator('#alertList')).to_contain_text('Resolved'); a.get_by_role('button',name='History',exact=False).click(); expect(a.locator('#alertList')).to_contain_text('Trade validation failure'); assert not errors,errors
                print('PASS: dismiss is local, history remains, no JS exceptions',flush=True)
                browser.close()
        finally:
            server.stopping.set(); server.store.wake(); server.shutdown(); server.server_close()

if __name__=='__main__': run()
