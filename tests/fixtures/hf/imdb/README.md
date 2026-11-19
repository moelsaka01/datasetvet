---
annotations_creators:
- expert-generated
language_creators:
- expert-generated
language:
- en
license:
- other
multilinguality:
- monolingual
size_categories:
- 10K<n<100K
source_datasets:
- original
task_categories:
- text-classification
task_ids:
- sentiment-classification
paperswithcode_id: imdb-movie-reviews
pretty_name: IMDB
dataset_info:
  config_name: plain_text
  features:
  - name: text
    dtype: string
  - name: label
    dtype:
      class_label:
        names:
          '0': neg
          '1': pos
  splits:
  - name: train
    num_bytes: 33432823
    num_examples: 25000
  - name: test
    num_bytes: 32650685
    num_examples: 25000
  - name: unsupervised
    num_bytes: 67106794
    num_examples: 50000
  download_size: 83446840
  dataset_size: 133190302
configs:
- config_name: plain_text
  data_files:
  - split: train
    path: plain_text/train-*
  - split: test
    path: plain_text/test-*
  - split: unsupervised
    path: plain_text/unsupervised-*
  default: true
train-eval-index:
- config: plain_text
  task: text-classification
  task_id: binary_classification
  splits:
    train_split: train
    eval_split: test
  col_mapping:
    text: text
    label: target
  metrics:
  - type: accuracy
  - name: Accuracy
  - type: f1
    name: F1 macro
    args:
      average: macro
  - type: f1
    name: F1 micro
    args:
      average: micro
  - type: f1
    name: F1 weighted
    args:
      average: weighted
  - type: precision
    name: Precision macro
    args:
      average: macro
  - type: precision
    name: Precision micro
    args:
      average: micro
  - type: precision
    name: Precision weighted
    args:
      average: weighted
  - type: recall
    name: Recall macro
    args:
      average: macro
  - type: recall
    name: Recall micro
    args:
      average: micro
  - type: recall
    name: Recall weighted
    args:
      average: weighted
---
