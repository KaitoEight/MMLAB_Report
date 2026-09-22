/** Read API failures from FastAPI, Starlette and non-JSON proxy responses. */
export async function readApiResponse(response:Response):Promise<any>{
 let data:any=null;
 try { data=await response.json(); } catch { /* An HTML/plain-text error is not JSON. */ }
 if(!response.ok){
  const details=typeof data?.error==='string'?data.error:typeof data?.detail==='string'?data.detail:
   Array.isArray(data?.detail)?data.detail.map((e:any)=>`${Array.isArray(e.loc)?e.loc.join('.'):'Dữ liệu'}: ${e.msg||'Không hợp lệ'}`).join('; '):'';
  const hint=response.status===405?'Server không hỗ trợ thao tác này. Dừng ứng dụng, cập nhật cả backend và frontend rồi khởi động lại. Nếu vẫn lỗi, kiểm tra cấu hình proxy.':
   response.status===401?'Phiên admin đã hết hạn. Vui lòng đăng nhập lại.':
   response.status===404?'Không tìm thấy báo cáo hoặc API. Tải lại danh sách; kiểm tra backend đã cập nhật.':
   response.status===422?'Server không chấp nhận dữ liệu gửi lên.':
   response.status>=500?'Lỗi phía server. Xem lỗi trong cửa sổ chạy run_local.py.':'Yêu cầu không thành công.';
  throw Error(`HTTP ${response.status}: ${details?details+'. ':''}${hint}`);
 }
 if(data===null)throw Error(`HTTP ${response.status}: Server không trả JSON. Kiểm tra địa chỉ API/proxy đang trỏ đúng backend.`);
 return data;
}
