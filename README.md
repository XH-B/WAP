# WAP
Offline Handwritten Math Expression Recognizer




# dataset
https://github.com/jmwang66/WAP-implemented-by-Pytorch/tree/master/data
# Improvement
The purpose of this experiment is just to decrease the valid experiment time.
In the trainging, not use beam_search to change the learning rate, since it is slow. we use loss to change the learning rate. and the effect is same. but it is 10 times faster than before.

```
python train_wap_lr.py
```

I should notice I just run train_wap_lr.py and got 51.78% and did not run train_wap.py by myself. 



'faster 10 '
|       | wap   | ours |
| ---------- | :-----------:  | :-----------: |
|result Exprate    | 51.~%    | 51.78% |
|valid time| 133 S | 13 S |




