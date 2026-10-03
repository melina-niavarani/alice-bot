import {zipSync,strToU8} from 'fflate';

type ExportMember={id:string;name:string;platform:string;created:string;status:string;isOwner:boolean};
const statusLabels:Record<string,string>={active:'دریافت پیام فعال',stopped:'توقف دریافت به درخواست عضو',unavailable:'ارسال فعلاً ممکن نیست'};
// Every value is an inline string: names cannot become spreadsheet formulas.
const xml=(value:unknown)=>String(value??'').replace(/[\u0000-\u0008\u000B\u000C\u000E-\u001F]/g,'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&apos;');
export function membersXlsx(members:ExportMember[]){
  const rows=[['نام نمایشی','پیام‌رسان','شناسه حساب','تاریخ ثبت در بات (تهران)','وضعیت دریافت پیام','نقش'],
    ...members.map(m=>{
      const date=new Date(m.created.endsWith('Z')?m.created:m.created.replace(' ','T')+'Z');
      return [m.name,m.platform==='bale'?'بله':'تلگرام',m.id,
        Number.isFinite(date.getTime())?new Intl.DateTimeFormat('fa-IR',{timeZone:'Asia/Tehran',dateStyle:'medium',timeStyle:'short'}).format(date):'',
        statusLabels[m.status]||m.status,m.isOwner?'مدیر':'عضو'];
    })];
  const sheetRows=rows.map((row,i)=>`<row r="${i+1}" ht="24" customHeight="1">${row.map((value,j)=>`<c r="${String.fromCharCode(65+j)}${i+1}" t="inlineStr" s="${i===0?1:0}"><is><t xml:space="preserve">${xml(value)}</t></is></c>`).join('')}</row>`).join('');
  const parts:Record<string,string>={
    '[Content_Types].xml':`<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/></Types>`,
    '_rels/.rels':`<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>`,
    'xl/workbook.xml':`<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="اعضای بات‌های آلیس" sheetId="1" r:id="rId1"/></sheets></workbook>`,
    'xl/_rels/workbook.xml.rels':`<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>`,
    'xl/styles.xml':`<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><fonts count="2"><font><sz val="11"/><name val="Arial"/></font><font><b/><sz val="11"/><color rgb="FFFFFFFF"/><name val="Arial"/></font></fonts><fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FF1A507F"/><bgColor indexed="64"/></patternFill></fill></fills><borders count="1"><border/></borders><cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs><cellXfs count="2"><xf numFmtId="49" fontId="0" fillId="0" borderId="0" xfId="0" applyAlignment="1"><alignment vertical="center" readingOrder="2"/></xf><xf numFmtId="49" fontId="1" fillId="2" borderId="0" xfId="0" applyAlignment="1"><alignment vertical="center" horizontal="center" readingOrder="2"/></xf></cellXfs><cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>`,
    'xl/worksheets/sheet1.xml':`<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><dimension ref="A1:F${rows.length}"/><sheetViews><sheetView workbookViewId="0" rightToLeft="1" showGridLines="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews><cols><col min="1" max="1" width="34" customWidth="1"/><col min="2" max="3" width="20" customWidth="1"/><col min="4" max="5" width="38" customWidth="1"/><col min="6" max="6" width="14" customWidth="1"/></cols><sheetData>${sheetRows}</sheetData><autoFilter ref="A1:F${rows.length}"/></worksheet>`,
  };
  return zipSync(Object.fromEntries(Object.entries(parts).map(([name,content])=>[name,strToU8('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'+content)])),{level:1});
}
