"""Real Google OAuth + Sheets adapter. Fixed outbound hosts; no browser tokens.
No mocked success or automatic write retry is permitted in this adapter.
"""
from dataclasses import dataclass, field
from decimal import Decimal
import json, re, time, threading
from urllib.parse import quote
import httpx
from .security import seal, unseal

SCOPE='https://www.googleapis.com/auth/spreadsheets'
TOKEN_URL='https://oauth2.googleapis.com/token'
SHEETS='https://sheets.googleapis.com/v4/spreadsheets/'
class GoogleError(Exception):
    def __init__(self,message,status=0,ambiguous=False):
        super().__init__(message); self.status=status; self.ambiguous=ambiguous

@dataclass
class Cell:
    value: object=''
    formatted: str=''
    formula: str=''
    derived: bool=False
    error: bool=False
@dataclass
class Snapshot:
    spreadsheet_id: str
    sheet_id: int
    title: str
    rows: list[list[Cell]]
    protected: list[dict]=field(default_factory=list)
    merges: list[dict]=field(default_factory=list)
    dynamic_formula: bool=False
    def value(self,row,col):
        return self.rows[row][col].value if row<len(self.rows) and col<len(self.rows[row]) else ''
    def cell(self,row,col):
        return self.rows[row][col] if row<len(self.rows) and col<len(self.rows[row]) else Cell()

class GoogleSheets:
    _lock=threading.RLock()
    _last_request=0.0
    def __init__(self,settings,credential,http_client=None):
        self.settings=settings
        self.tokens=json.loads(unseal(settings,credential))
        self.http=http_client or httpx.Client(timeout=httpx.Timeout(35,connect=10),follow_redirects=False)
    def _token(self):
        with self._lock:
            if self.tokens.get('access_token') and self.tokens.get('expires_at',0)>time.time()+60:
                return self.tokens['access_token']
            try:
                r=self.http.post(TOKEN_URL,data={'client_id':self.settings.google_client_id,
                    'client_secret':self.settings.google_client_secret,'refresh_token':self.tokens['refresh_token'],
                    'grant_type':'refresh_token'})
            except httpx.HTTPError: raise GoogleError('Google authorization service is unavailable.')
            if r.status_code!=200: raise GoogleError('Google authorization expired or was revoked. Reconnect the account.',r.status_code)
            t=r.json()
            self.tokens.update(access_token=t['access_token'],expires_at=time.time()+t.get('expires_in',3600))
            return self.tokens['access_token']
    def _request(self,method,path,**kwargs):
        token=self._token()
        # One process-wide quota budget. The application uses a single elected worker.
        with self._lock:
            delay=1.2-(time.monotonic()-self._last_request)
            if delay>0: time.sleep(delay)
            type(self)._last_request=time.monotonic()
        try:
            r=self.http.request(method,SHEETS+path,headers={'Authorization':'Bearer '+token},**kwargs)
        except httpx.HTTPError:
            raise GoogleError('Google request timed out or connection failed.',ambiguous=method!='GET')
        if r.status_code>=400:
            message={401:'Google authorization expired. Reconnect.',403:'Google denied file access or quota. Check private sharing and enabled API.',
                404:'Spreadsheet or tab not found.',429:'Google quota exceeded; retry is scheduled.'}.get(r.status_code,'Google returned an error; no automatic write replay.')
            raise GoogleError(message,r.status_code,ambiguous=method!='GET' and r.status_code>=500)
        return r.json()
    def metadata(self,spreadsheet_id):
        if not re.fullmatch(r'[A-Za-z0-9_-]{20,180}',spreadsheet_id): raise GoogleError('Invalid spreadsheet ID.')
        return self._request('GET',spreadsheet_id,params={'fields':'spreadsheetId,properties(title,locale,timeZone),sheets(properties,protectedRanges,merges)'})
    def snapshot(self,spreadsheet_id,sheet_id,max_rows=10000,max_columns=101):
        meta=self.metadata(spreadsheet_id)
        sheet=next((s for s in meta.get('sheets',[]) if s['properties']['sheetId']==sheet_id),None)
        if not sheet: raise GoogleError('Configured numeric tab ID no longer exists.')
        props=sheet['properties']; title=props['title']; grid=props.get('gridProperties',{})
        row_count=grid.get('rowCount',1000)
        if row_count>max_rows: raise GoogleError(f'Tab grid has {row_count} rows, above the approved {max_rows}-row scan cap. Increase the mapping cap after review.')
        if grid.get('columnCount',26)>max_columns:
            # Only mapped columns are needed, but all formulas must be inspected for spill protection.
            raise GoogleError(f'Tab has more than {max_columns} columns. Expand adapter review before import; no silent truncation.')
        all_rows=[]; dynamic=False
        for start in range(0,row_count,1000):
            end=min(start+1000,row_count)
            def col_name(index):
                out=''
                while index:
                    index,rem=divmod(index-1,26); out=chr(65+rem)+out
                return out
            last_col=col_name(grid.get('columnCount',26))
            rng="'"+title.replace("'","''")+f"'!A{start+1}:{last_col}{end}"
            data=self._request('GET',spreadsheet_id,params={'ranges':rng,'includeGridData':'true',
                'fields':'sheets(data(startRow,startColumn,rowData(values(userEnteredValue,effectiveValue,formattedValue))))'})
            parts=data.get('sheets',[{}])[0].get('data',[])
            rows=[[] for _ in range(end-start)]
            for part in parts:
                offset=part.get('startRow',start)-start
                for ri,raw in enumerate(part.get('rowData',[])):
                    cells=[]
                    for c in raw.get('values',[]):
                        entered=c.get('userEnteredValue',{}); effective=c.get('effectiveValue',{})
                        formula=entered.get('formulaValue','')
                        if formula and re.search(r'\b(ARRAYFORMULA|FILTER|SORT|SORTN|UNIQUE|SEQUENCE|QUERY|SPLIT|TRANSPOSE|IMPORTRANGE|GOOGLEFINANCE)\s*\(',formula,re.I): dynamic=True
                        val=effective.get('stringValue',effective.get('numberValue',effective.get('boolValue','')))
                        cells.append(Cell(val,c.get('formattedValue',str(val)),formula,bool(effective and not entered), 'errorValue' in effective))
                    if 0<=ri+offset<len(rows): rows[ri+offset]=cells
            all_rows.extend(rows)
        while all_rows and not any(c.value!='' or c.formula for c in all_rows[-1]): all_rows.pop()
        return Snapshot(spreadsheet_id,sheet_id,title,all_rows,sheet.get('protectedRanges',[]),sheet.get('merges',[]),dynamic)
    def write_cell(self,spreadsheet_id,sheet_id,row,col,value,is_money=False):
        entered={'numberValue':float(Decimal(str(value)))} if is_money else {'stringValue':str(value)}
        body={'requests':[{'updateCells':{'start':{'sheetId':sheet_id,'rowIndex':row,'columnIndex':col},
               'rows':[{'values':[{'userEnteredValue':entered}]}],'fields':'userEnteredValue'}}]}
        self._request('POST',spreadsheet_id+':batchUpdate',json=body)

def inside(rng,sheet_id,row,col):
    return rng.get('sheetId',sheet_id)==sheet_id and rng.get('startRowIndex',0)<=row<rng.get('endRowIndex',2**31) and rng.get('startColumnIndex',0)<=col<rng.get('endColumnIndex',2**31)
def writable(snapshot,row,col):
    cell=snapshot.cell(row,col)
    if cell.formula or cell.derived or cell.error: return False,'Formula, derived, or error cell cannot be written.'
    if snapshot.dynamic_formula: return False,'Dynamic/array formula detected in this tab. Write-back is conservatively blocked.'
    if any(inside(r,snapshot.sheet_id,row,col) for r in snapshot.merges): return False,'Merged cell is read-only.'
    for p in snapshot.protected:
        if inside(p.get('range',{}),snapshot.sheet_id,row,col):
            if not any(inside(r,snapshot.sheet_id,row,col) for r in p.get('unprotectedRanges',[])):
                return False,'Protected cell is read-only, including warning-only protection.'
    return True,''
