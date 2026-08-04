"""JS dùng chung cho hai nút trợ lý: **Gợi ý trả lời** (RAG+LLM) và **Trích tri
thức** (GPT đề xuất cặp hỏi-đáp).

Vì sao tách riêng: hai màn dùng chung tính năng này — Tin nhắn (`/tin-nhan`) và
Hội thoại (`/crm/hoi-thoai`). Chép đôi ~240 dòng JS thì sớm muộn hai bản lệch
nhau; để một chỗ thì sửa một lần ăn cả hai.

Cả hai màn gọi CÙNG ba endpoint có sẵn (`/tin-nhan/goi-y`,
`/tin-nhan/trich-tri-thuc`, `.../luu`) nên không phát sinh đường xử lý thứ hai.

Cách dùng: nhúng `TRO_LY_JS` vào trang rồi gọi

    window.__troly(form, field);

* `form`  — form soạn tin, phải có input ẩn `page_id` · `conv_id` · `customer_id`
* `field` — ô nhập để đổ câu gợi ý vào (`<textarea>` hoặc `<input>`)

Trang phải có sẵn 4 phần tử theo id: `btn-suggest` · `suggest-hint` ·
`btn-extract` · `extract-panel`.
"""

TRO_LY_JS = """
window.__troly = function (troly_form, troly_field) {
  var sug = document.getElementById('btn-suggest');
  var hint = document.getElementById('suggest-hint');
  var extBtn = document.getElementById('btn-extract');
  var extPanel = document.getElementById('extract-panel');

    // Nút "Gợi ý trả lời": gọi RAG+LLM cho tin cuối của khách, đổ vào ô soạn để
    // người sửa rồi tự bấm Gửi. KHÔNG tự gửi. Đọc page_id/conv_id/customer_id từ
    // chính các input ẩn của composer (một nguồn dữ liệu duy nhất).
    if (sug) {
      sug.addEventListener('click', function(){
        var f = troly_form;
        var body = new URLSearchParams({
          page_id: (f && f.page_id) ? f.page_id.value : '',
          conv_id: (f && f.conv_id) ? f.conv_id.value : '',
          customer_id: (f && f.customer_id) ? f.customer_id.value : ''
        });
        var old = sug.textContent;
        sug.disabled = true; sug.textContent = 'Đang soạn…';
        if (hint) { hint.textContent = ''; hint.classList.remove('warn'); }
        fetch('/tin-nhan/goi-y', {
          method: 'POST',
          headers: {'Content-Type': 'application/x-www-form-urlencoded'},
          body: body.toString()
        })
        .then(function(r){ return r.json().catch(function(){ return {error:'Lỗi máy chủ'}; }); })
        .then(function(d){
          sug.disabled = false; sug.textContent = old;
          if (!d || d.error) {
            if (hint) { hint.textContent = '⚠ ' + ((d && d.error) || 'Không gợi ý được'); hint.classList.add('warn'); }
            return;
          }
          if (d.no_match || !d.reply) {   // câu hỏi chưa có trong tri thức -> KHÔNG gợi ý
            if (hint) {
              hint.textContent = d.nguon_text || 'Câu hỏi này chưa có trong tri thức — không gợi ý.';
              hint.classList.add('warn');
            }
            return;   // giữ nguyên ô soạn, không ghi đè
          }
          troly_field.value = d.reply;
          // <textarea> ở màn Tin nhắn thì nới cao theo nội dung; <input> ở màn
          // Hội thoại không có scrollHeight kiểu đó nên bỏ qua.
          if (troly_field.tagName === 'TEXTAREA') {
            troly_field.style.height = 'auto';
            troly_field.style.height = Math.min(troly_field.scrollHeight, 130) + 'px';
          }
          troly_field.focus();
          if (hint) hint.textContent = d.nguon_text || '';
        })
        .catch(function(){
          sug.disabled = false; sug.textContent = old;
          if (hint) { hint.textContent = '⚠ Lỗi mạng, thử lại.'; hint.classList.add('warn'); }
        });
      });
    }

    // Nút "Trích tri thức": đọc TOÀN BỘ hội thoại đang mở, gọi GPT đề xuất các
    // cặp hỏi-đáp (KHÔNG ghi DB) rồi hiện màn xem/sửa/bỏ từng dòng — chỉ dòng
    // người dùng bấm Lưu mới thật sự vào hoi_thoai_mau (human-in-the-loop, tri
    // thức y tế không được tự động vào kho mà chưa ai duyệt).

    function extractRow(item){
      var wrap = document.createElement('div');
      wrap.className = 'card ext-row';
      wrap.style.marginBottom = '10px';

      var head = document.createElement('label');
      head.className = 'check';
      var chk = document.createElement('input');
      chk.type = 'checkbox'; chk.checked = true; chk.className = 'ext-on';
      head.appendChild(chk);
      head.appendChild(document.createTextNode('Lưu cặp này'));
      wrap.appendChild(head);

      var qLabel = document.createElement('label');
      qLabel.appendChild(document.createTextNode('Câu hỏi'));
      var qTa = document.createElement('textarea');
      qTa.rows = 2; qTa.className = 'ext-q';
      qTa.value = (item && item.cau_hoi) || '';       // .value -> an toàn, không parse HTML
      qLabel.appendChild(qTa);
      wrap.appendChild(qLabel);

      var aLabel = document.createElement('label');
      aLabel.appendChild(document.createTextNode('Câu trả lời'));
      var aTa = document.createElement('textarea');
      aTa.rows = 3; aTa.className = 'ext-a';
      aTa.value = (item && item.cau_tra_loi) || '';
      aLabel.appendChild(aTa);
      wrap.appendChild(aLabel);

      var nLabel = document.createElement('label');
      nLabel.appendChild(document.createTextNode('Nguồn'));
      var nIn = document.createElement('input');
      nIn.className = 'ext-n'; nIn.value = 'chat_that';
      nLabel.appendChild(nIn);
      wrap.appendChild(nLabel);

      return wrap;
    }

    function closeExtract(){ extPanel.innerHTML = ''; }

    // Thanh đầu bảng: tiêu đề + nút ✕ Đóng. Có ở MỌI trạng thái (lỗi / không có
    // đề xuất / đã lưu / chưa lưu) vì bảng nằm chen giữa khung chat và ô soạn tin
    // — không đóng được thì vướng chỗ trả lời khách.
    function extractHead(){
      var head = document.createElement('div');
      head.className = 'ext-head';
      var title = document.createElement('b');
      title.textContent = '🧠 Trích tri thức';
      var x = document.createElement('button');
      x.type = 'button'; x.className = 'btn ext-close';
      x.textContent = '✕ Đóng';
      x.title = 'Đóng bảng trích tri thức';
      x.addEventListener('click', closeExtract);
      head.appendChild(title);
      head.appendChild(x);
      return head;
    }

    function renderExtractPanel(d){
      extPanel.innerHTML = '';
      if (!d) return;
      var box = document.createElement('div');
      box.className = 'card form';
      box.style.marginTop = '10px';
      box.appendChild(extractHead());
      if (d.error) {
        var err = document.createElement('div');
        err.className = 'flash err';
        err.textContent = '✕ ' + d.error;
        box.appendChild(err);
        extPanel.appendChild(box);
        return;
      }
      var items = d.items || [];
      if (!items.length) {
        var p = document.createElement('p');
        p.className = 'intro';
        p.textContent = d.note || 'Không có đề xuất nào.';
        box.appendChild(p);
        extPanel.appendChild(box);
        return;
      }
      var intro = document.createElement('p');
      intro.className = 'intro';
      intro.textContent = 'GPT đề xuất ' + items.length + ' cặp hỏi-đáp từ hội '
        + 'thoại này — xem/sửa rồi bấm Lưu (bỏ tick dòng nào không muốn lưu).';
      box.appendChild(intro);
      for (var i = 0; i < items.length; i++) box.appendChild(extractRow(items[i]));

      var actions = document.createElement('div');
      actions.style.cssText = 'display:flex;gap:10px;align-items:center;margin-top:6px';
      var saveBtn = document.createElement('button');
      saveBtn.type = 'button'; saveBtn.className = 'btn primary';
      saveBtn.textContent = '💾 Lưu các mục đã chọn';
      // Nút đóng thứ 2 ở CUỐI bảng: danh sách đề xuất có thể dài, lưu xong mà
      // phải cuộn ngược lên đầu mới đóng được thì rất vướng.
      var closeBtn = document.createElement('button');
      closeBtn.type = 'button'; closeBtn.className = 'btn';
      closeBtn.textContent = '✕ Đóng';
      closeBtn.addEventListener('click', closeExtract);
      var resultSpan = document.createElement('span');
      resultSpan.className = 'shint';
      actions.appendChild(saveBtn);
      actions.appendChild(closeBtn);
      actions.appendChild(resultSpan);
      box.appendChild(actions);

      saveBtn.addEventListener('click', function(){
        var rows = box.querySelectorAll('.ext-row');
        var payload = [];
        for (var i = 0; i < rows.length; i++) {
          var row = rows[i];
          if (!row.querySelector('.ext-on').checked) continue;
          var q = row.querySelector('.ext-q').value.trim();
          var a = row.querySelector('.ext-a').value.trim();
          var n = row.querySelector('.ext-n').value.trim();
          if (q && a) payload.push({cau_hoi: q, cau_tra_loi: a, nguon: n});
        }
        if (!payload.length) {
          resultSpan.classList.add('warn');
          resultSpan.textContent = 'Chưa chọn dòng nào để lưu.';
          return;
        }
        var oldTxt = saveBtn.textContent;
        saveBtn.disabled = true; saveBtn.textContent = 'Đang lưu…';
        fetch('/tin-nhan/trich-tri-thuc/luu', {
          method: 'POST',
          headers: {'Content-Type': 'application/x-www-form-urlencoded'},
          body: new URLSearchParams({items: JSON.stringify(payload)}).toString()
        })
        .then(function(r){ return r.json().catch(function(){ return {error:'Lỗi máy chủ'}; }); })
        .then(function(res){
          saveBtn.disabled = false; saveBtn.textContent = oldTxt;
          if (!res || res.error) {
            resultSpan.classList.add('warn');
            resultSpan.textContent = '⚠ ' + ((res && res.error) || 'Lỗi khi lưu');
            return;
          }
          resultSpan.classList.remove('warn');
          resultSpan.textContent = '✓ Đã lưu ' + res.saved + ' cặp hỏi-đáp'
            + ((res.errors && res.errors.length) ? ' (lỗi ' + res.errors.length + ' dòng)' : '') + '.';
        })
        .catch(function(){
          saveBtn.disabled = false; saveBtn.textContent = oldTxt;
          resultSpan.classList.add('warn');
          resultSpan.textContent = '⚠ Lỗi mạng, thử lại.';
        });
      });

      extPanel.appendChild(box);
    }

    if (extBtn && extPanel) {
      extBtn.addEventListener('click', function(){
        var f = troly_form;
        var body = new URLSearchParams({
          page_id: (f && f.page_id) ? f.page_id.value : '',
          conv_id: (f && f.conv_id) ? f.conv_id.value : '',
          customer_id: (f && f.customer_id) ? f.customer_id.value : ''
        });
        var old = extBtn.textContent;
        extBtn.disabled = true; extBtn.textContent = 'Đang phân tích…';
        extPanel.innerHTML = '';
        fetch('/tin-nhan/trich-tri-thuc', {
          method: 'POST',
          headers: {'Content-Type': 'application/x-www-form-urlencoded'},
          body: body.toString()
        })
        .then(function(r){ return r.json().catch(function(){ return {error:'Lỗi máy chủ'}; }); })
        .then(function(d){
          extBtn.disabled = false; extBtn.textContent = old;
          renderExtractPanel(d);
        })
        .catch(function(){
          extBtn.disabled = false; extBtn.textContent = old;
          renderExtractPanel({error: 'Lỗi mạng, thử lại.'});
        });
      });
    }


};
"""
