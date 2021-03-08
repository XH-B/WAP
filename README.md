# WAP
Offline Handwritten Math Expression Recognizer


# dataset
https://github.com/jmwang66/WAP-implemented-by-Pytorch/tree/master/data
# Improvement

In the trainging, not use beam_search to change the learning rate, since it is slow. we use loss to change the learning rate. and the effect is same. but it is 10 times faster than before.

python train_wap_lr.py

the stting is 

'faster 10 '
|       | wap   | ours |
| ---------- | :-----------:  | :-----------: |
|result Exprate    | 51.~%    | 51.78% |
|time| 133S | 13S |


