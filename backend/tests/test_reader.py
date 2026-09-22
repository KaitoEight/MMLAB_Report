import contextlib, io, json, tempfile, unittest
from email.message import EmailMessage
from pathlib import Path
from unittest.mock import patch
import imap_fetch as reader

def mail(authors='Hoàng Phong, Đang Van Thin', extra='', role='Co author'):
    msg=EmailMessage();msg['From']='Đặng Văn Thìn <thindv@uit.edu.vn>';msg['Subject']='Fwd: Research decision';msg['Message-ID']='<fixture@example.test>'
    msg.set_content(f'Type of Report: Paper\nTitle of Work: A study of Arabic stance\nAll authors: {authors}\nVenue: ArabicNLP 2026\nRole: {role}\nIndex: Scopus\nRanking: C-Unranked\n{extra}\n--- Forwarded message ---\nTo: tiepnv@uit.edu.vn\nDecision: Accept')
    return msg.as_bytes()

class ReaderTests(unittest.TestCase):
    def test_mapping_and_forward(self):
        r=reader.analyze(mail(),'imap:fixture:1','2026-09-02T17:26:00+07:00')['report']
        self.assertTrue(r['isValid']);self.assertTrue(r['forwarded']);self.assertEqual(r['memberIds'],[2]);self.assertEqual(r['memberId'],2);self.assertEqual(r['role'],'Co-author');self.assertEqual(r['status'],'Accepted')
    def test_multiple_members_keep_one_reporter(self):
        r=reader.analyze(mail('Dang Van Thin, Vinh-Tiep Nguyen'),'x','2026-09-02T00:00:00+07:00')['report']
        self.assertEqual(r['memberIds'],[1,2]);self.assertEqual(r['memberId'],2)
    def test_explicit_person_in_charge(self):
        r=reader.analyze(mail('Dang Van Thin, Vinh-Tiep Nguyen','Person in Charge: tiepnv@uit.edu.vn'),'x','2026-09-02T00:00:00+07:00')['report']
        self.assertEqual(r['memberId'],1);self.assertTrue(r['isValid'])
    def test_errors_do_not_drop_report(self):
        r=reader.analyze(mail(role='Wrong role'),'x','2026-09-02T00:00:00+07:00')['report']
        self.assertFalse(r['isValid']);self.assertEqual(r['invalidFields'][0]['field'],'Role')
    def test_external_sender_is_not_author(self):
        r=reader.analyze(mail('External Author'),'x','2026-09-02T00:00:00+07:00')['report']
        self.assertIsNone(r['memberId']);self.assertEqual(r['memberIds'],[])
    def test_irrelevant_email(self):
        msg=EmailMessage();msg['Subject']='Fwd: Hello';msg.set_content('A personal hello')
        result=reader.analyze(msg.as_bytes(),'x','2026-09-02T00:00:00+07:00')
        self.assertEqual(result['state'],'ignored');self.assertNotIn('A personal hello',json.dumps(result))
    def test_forward_without_template_is_reviewed(self):
        msg=EmailMessage();msg['Subject']='Fwd: Your submission has been accepted';msg.set_content('Dear authors, your paper has been accepted.')
        result=reader.analyze(msg.as_bytes(),'x','2026-09-02T00:00:00+07:00')
        self.assertEqual(result['state'],'reported');self.assertEqual(result['report']['type'],'Paper');self.assertFalse(result['report']['isValid'])
    def test_unknown_category_review(self):
        msg=EmailMessage();msg.set_content('Type of Report: Patent\nTitle of Work: New invention')
        self.assertEqual(reader.analyze(msg.as_bytes(),'x','2026-09-02T00:00:00+07:00')['state'],'review')
    def test_internaldate_timezone(self):
        self.assertEqual(reader.received_date(b'1 (INTERNALDATE "30-Jun-2026 20:00:00 +0000")'),'2026-07-01T03:00:00+07:00')
    def test_internaldate_missing_rejected(self):
        with self.assertRaises(ValueError):reader.received_date(b'1 (RFC822.SIZE 30)')
    def test_monthly_preserves_tasks(self):
        msg=EmailMessage();msg['Subject']='Báo cáo tháng 9/2026';msg['From']='thindv@uit.edu.vn';msg.set_content('Đã:\n01/09, Train model\nSẽ:\nSubmit paper')
        r=reader.analyze(msg.as_bytes(),'x','2026-10-01T00:00:00+07:00')['report']
        self.assertEqual(r['reportPeriod'],'2026-10');self.assertEqual(r['date'],'2026-10-01');self.assertEqual(r['monthlyTasks']['done'][0]['content'],'Train model')
    def test_imap_readonly_and_cache(self):
        class Fake:
            calls=[]
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def login(self,*args):self.calls.append(('login',))
            def select(self,folder,readonly=False):self.calls.append(('select',folder,readonly));return 'OK',[b'1']
            def response(self,name):return 'UIDVALIDITY',[b'123']
            def uid(self,operation,*args):
                self.calls.append((operation,*args))
                if operation=='search':return 'OK',[b'17']
                if args[-1]=='(RFC822.SIZE INTERNALDATE)':return 'OK',[b'1 (UID 17 RFC822.SIZE 1000 INTERNALDATE "02-Sep-2026 17:26:00 +0700")']
                if args[-1]=='(BODY.PEEK[])':return 'OK',[(b'1 (BODY[] {1000}',mail()),b')']
                raise AssertionError('Unexpected write/fetch operation')
        with tempfile.TemporaryDirectory() as temp,patch.object(reader.imaplib,'IMAP4_SSL',return_value=Fake()),contextlib.redirect_stdout(io.StringIO()):
            out=Path(temp);first=reader.fetch_once('mmlab@uit.edu.vn','fake-password','INBOX',out);second=reader.fetch_once('mmlab@uit.edu.vn','fake-password','INBOX',out)
            self.assertEqual(first['reports'],1);self.assertEqual(second['reports'],1);self.assertIn(('select','INBOX',True),Fake.calls)
            self.assertEqual(sum(c[0]=='fetch' and c[-1]=='(BODY.PEEK[])' for c in Fake.calls),1)
            export=json.loads((out/'mmlab_export.json').read_text(encoding='utf-8'));self.assertEqual(export['schema_version'],reader.VERSION);self.assertNotIn('fake-password',(out/'mmlab_export.json').read_text(encoding='utf-8'));self.assertEqual(export['summary']['processed'],1)

if __name__=='__main__':unittest.main()
