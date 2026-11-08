# ZEN Python binding — kiểm tra hợp đồng ngày 11/10/2026

Đã chạy [script tái hiện](../../scripts/spike_zen_contract.py) bằng Python trong `agent3_tax_compliance/venv`, zen-engine **0.53.0**. Không cài/nâng cấp SDK, không sửa JDM hay backend; kết quả chỉ áp dụng cho binding/phiên bản này.

Chạy từ thư mục gốc workspace:

```powershell
.\agent3_tax_compliance\venv\Scripts\python.exe .\scripts\spike_zen_contract.py
```

| Probe | Quan sát |
|---|---|
| Python Decimal trong context | TypeError: unsupported type Decimal |
| Decimal string + numeric literal | RuntimeError: Unsupported type |
| `0.1 + 0.2` | Python float 0.3; ca đơn lẻ này không chứng minh Decimal an toàn |
| `9007199254740992 + 1` | Python float 9007199254740992.0, mất đơn vị tăng |
| evaluate với trace=true trên JDM hiện có | Node input/output và traceData theo row khớp |
| Row traceData | index, reference_map, rule; không có mảng boolean từng condition như schema minh họa của NEW_PLAN |

Probe trace dùng input_complete=false, normalize blank/boolean cells giống adapter hiện có. Row `r_missing` trả REVIEW. Đây là kiểm tra shape/khả năng kỹ thuật, không kiểm định tính đúng pháp luật của rule CIT trong JDM.

Quyết định thiết kế: chưa cho tiền dạng Decimal hoặc string đi thẳng vào engine như thể sẽ tính chính xác. Wrapper cần money boundary có giới hạn miền/range và precision đã kiểm chứng, hoặc tính các predicate số tiền bằng Decimal phía Python rồi truyền typed facts với evidence vào ZEN. Integer minor units cũng phải qua kiểm thử vì binding có thể làm mất độ chính xác khi số lớn. Không chỉ đổi JSON string thành float. Pin SDK và chạy lại spike khi nâng phiên bản.

Trace chuẩn của sản phẩm cần wrapper normalization/instrumentation với condition IDs, row IDs và phiên bản expression. Giữ raw trace; không giả mọi condition của non-matching rows đã được quan sát. Khi instrument condition bằng evaluator riêng, lưu evaluation_mode/version và chứng minh tương đương predicate engine; không gắn nhãn ENGINE_OBSERVED cho kết quả tự tính.

Tài liệu sơ cấp tham khảo: [repository GoRules ZEN](https://github.com/gorules/zen), [Python binding](https://github.com/gorules/zen/tree/master/bindings/python). README nhánh master có thể khác 0.53.0; quan sát runtime ở trên mới là evidence cho môi trường hiện tại.
