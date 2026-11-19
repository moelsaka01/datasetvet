---
license: mit
dataset_info:
  features:
  - name: id
    dtype: string
  - name: question
    dtype: string
  - name: image
    dtype: string
  - name: image_preview
    dtype: image
  - name: answer
    dtype: string
  - name: answer_type
    dtype: string
  - name: author_name
    dtype: string
  - name: rationale
    dtype: string
  - name: rationale_image
    dtype: image
  - name: raw_subject
    dtype: string
  - name: category
    dtype: string
  - name: canary
    dtype: string
  splits:
  - name: test
    num_bytes: 284205983.0
    num_examples: 2500
  download_size: 274276147
  dataset_size: 284205983.0
configs:
- config_name: default
  data_files:
  - split: test
    path: data/test-*
---
