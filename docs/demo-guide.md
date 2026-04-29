# 本地演示指南

## 1. 启动项目

```bash
docker compose up -d --build api worker frontend
make check
```

## 2. 打开前端

```text
http://localhost:3000
```

## 3. 推荐演示流程

1. 注册账号
2. 登录
3. 创建个人知识库
4. 上传 `sample_docs/sample.txt`
5. 上传 `sample_docs/sample.md`
6. 再上传一个普通文本型 PDF
7. 等待文档状态变为 `indexed` 或界面显示“可问答”
8. 提问并查看 `answer + citations`
9. 修改 `RETRIEVAL_MIN_SCORE` 后重新提问，观察“无可靠来源”行为
10. 触发 `reindex`

## 4. 常见验证命令

```bash
docker compose ps
docker compose logs --tail=100 api
docker compose logs --tail=100 worker
docker compose exec db psql -U purelink -d purelink -c "select id, original_filename, processing_status from documents order by id desc limit 10;"
docker compose exec db psql -U purelink -d purelink -c "select id, document_id, status, current_step, error_code from processing_jobs order by id desc limit 10;"
docker compose exec db psql -U purelink -d purelink -c "select document_id, count(*) from document_chunks group by document_id order by document_id desc limit 10;"
```

## 5. 镜像轻量验证

```bash
docker images | grep purelink
docker compose exec -T worker python - <<'PY'
import importlib.util
for name in ["fastembed", "onnxruntime", "torch", "sentence_transformers", "transformers", "vosk", "cv2", "pytesseract"]:
    print(name, "FOUND" if importlib.util.find_spec(name) else "not installed")
PY
```

期望：

- `fastembed FOUND`
- `onnxruntime FOUND`
- `torch not installed`
- `sentence_transformers not installed`
- `transformers not installed`
- `vosk not installed`
- `cv2 not installed`
- `pytesseract not installed`

## 6. 运行态确认

```bash
docker compose exec worker sh -lc 'echo $EMBEDDING_PROVIDER && echo $EMBEDDING_MODEL'
```

期望输出：

```text
fastembed
BAAI/bge-small-zh-v1.5
```
