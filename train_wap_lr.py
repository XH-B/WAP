import time
import os
import re
import numpy as np
import random
import torch
from torch import optim, nn
from utils import dataIterator, load_dict, prepare_data, gen_sample, weight_init
from encoder_decoder import Encoder_Decoder

# whether use multi-GPUs
multi_gpu_flag = False
# whether init params
init_param_flag = True

os.environ['CUDA_VISIBLE_DEVICES'] = '0'
# use_pretrianed_model = True
# device_ids = [0,1,2]
# pretrained_model_path = './result_2/WAP_params169613_lr_0.0625.pkl' 

# load configurations
# paths

result_path = './result_9/'
if not os.path.exists(result_path):
    os.mkdir(result_path)
dictionaries = ['./data/dictionary.txt']
datasets = ['./data/offline-train.pkl', r'./data/train_caption.txt']
valid_datasets = ['./data/offline-test.pkl', './data/test_caption.txt']
valid_output = [result_path+ 'valid_decode_result.txt']
fpp_sample = open(valid_output[0], 'w')
valid_result = [result_path+ 'valid.wer']
saveto = result_path


# early stop
estop = False
halfLrFlag = 0
bad_counter = 0
finish_after = 10000000


patience = 15
lr_decrease_rate = 2
halfLrFlag_set = 10
lrate = 1



# training settings
if multi_gpu_flag:
    batch_Imagesize = 500000
    maxImagesize = 500000
    valid_batch_Imagesize = 500000
    batch_size = 96
    valid_batch_size = 24
else:
    batch_Imagesize = 320000
    maxImagesize = 320000
    valid_batch_Imagesize = 320000
    batch_size = 16
    valid_batch_size = 8



print('patence:',patience)
print('strat_lr:',lrate)
print('lr_decrease_rate:',lr_decrease_rate)
print('halfFlag:',halfLrFlag_set)
print('batch_size:',batch_size)
print('batch_size_valid:',valid_batch_size)
print('multi_gpu:',multi_gpu_flag)
print('os.environ:',os.environ['CUDA_VISIBLE_DEVICES'])
print('valid_out:',valid_output)
print('pretrained_use:',use_pretrianed_model)
print('pretrianed_model_path:',pretrained_model_path)

print('********'*10)
maxlen = 200
max_epochs = 5000

my_eps = 1e-6
decay_c = 1e-4
clip_c = 100.


# model architecture
params = {}
params['n'] = 256
params['m'] = 256
params['dim_attention'] = 512
params['D'] = 684
params['K'] = 111
params['growthRate'] = 24
params['reduction'] = 0.5
params['bottleneck'] = True
params['use_dropout'] = True
params['input_channels'] = 1

# load dictionary
worddicts = load_dict(dictionaries[0])
worddicts_r = [None] * len(worddicts)
for kk, vv in worddicts.items():
    worddicts_r[vv] = kk

# load data
train, train_uid_list = dataIterator(datasets[0], datasets[1], worddicts, batch_size=batch_size,
                                     batch_Imagesize=batch_Imagesize, maxlen=maxlen, maxImagesize=maxImagesize)

valid, valid_uid_list = dataIterator(valid_datasets[0], valid_datasets[1], worddicts, batch_size=valid_batch_size,
                                     batch_Imagesize=valid_batch_Imagesize, maxlen=maxlen, maxImagesize=maxImagesize)

# display
uidx = 0  # count batch
loss_s = 0.  # count loss
ud_s = 0  # time for training an epoch
validFreq = -1
saveFreq = -1
sampleFreq = -1
dispFreq = 100
if validFreq == -1:
    validFreq = len(train)
if saveFreq == -1:
    saveFreq = len(train)
if sampleFreq == -1:
    sampleFreq = len(train)

# initialize model
WAP_model = Encoder_Decoder(params)
if init_param_flag:
    WAP_model.apply(weight_init)
if multi_gpu_flag:
    WAP_model = nn.DataParallel(WAP_model, device_ids=device_ids)
WAP_model.cuda()

if use_pretrianed_model:
    print('***load_pretrained_model****')
    WAP_model.load_state_dict(torch.load(
            pretrained_model_path, map_location=lambda storage, loc: storage))

# print model's parameters
model_params = WAP_model.named_parameters()
# for k, v in model_params:
#     print(k)

# loss function
criterion = torch.nn.CrossEntropyLoss(reduce=False)
# optimizer
optimizer = optim.Adadelta(WAP_model.parameters(), lr=lrate, eps=my_eps, weight_decay=decay_c)

print('Optimization')

# statistics
history_errs = []
history_loss = []
min_Valid_WER=200
max_ExpRate=0

for eidx in range(max_epochs):
    print('epoch',eidx)
    n_samples = 0
    ud_epoch = time.time()
    random.shuffle(train)
    for x, y in train:
        WAP_model.train()
        ud_start = time.time()
        n_samples += len(x)
        uidx += 1
        x, x_mask, y, y_mask = prepare_data(params, x, y)

        x = torch.from_numpy(x).cuda()
        x_mask = torch.from_numpy(x_mask).cuda()
        y = torch.from_numpy(y).cuda()
        y_mask = torch.from_numpy(y_mask).cuda()

        # permute for multi-GPU training
        y = y.permute(1, 0)
        y_mask = y_mask.permute(1, 0)

        # forward
        scores, alphas = WAP_model(params, x, x_mask, y, y_mask)
        
        # recover from permute
        alphas = alphas.permute(1, 0, 2, 3)
        scores = scores.permute(1, 0, 2)
        scores = scores.contiguous()
        scores = scores.view(-1, scores.shape[2])
        y = y.permute(1, 0)
        y_mask = y_mask.permute(1, 0)
        y = y.contiguous()
        
        loss = criterion(scores, y.view(-1))
        loss = loss.view(y.shape[0], y.shape[1])
        loss = (loss * y_mask).sum(0) / y_mask.sum(0)
        loss = loss.mean()
        # loss = ((loss * y_mask).sum(0)).mean()
        loss_s += loss.item()

        # backward
        optimizer.zero_grad()
        loss.backward()
        if clip_c > 0.:
            torch.nn.utils.clip_grad_norm_(WAP_model.parameters(), clip_c)

        # update
        optimizer.step()

        ud = time.time() - ud_start
        ud_s += ud

        # display
        if np.mod(uidx, dispFreq) == 0:
            ud_s /= 60.
            loss_s /= dispFreq
            print('Epoch ', eidx, 'Update ', uidx, 'Cost ', loss_s, 'UD ', ud_s, 'lrate ', lrate, 'eps', my_eps,
                  'bad_counter', bad_counter)
            ud_s = 0
            loss_s = 0.

        # valid_loss
        if True:
            if np.mod(uidx, validFreq) == 0:  #len(train)
                print('valid loss start:************','valid_batch_size:',valid_batch_size,'valid_batch_len:',len(valid))
                valid_loss_start = time.time()
                loss_valid = 0.0
                valid_count_batch = 0 
                WAP_model.eval()
                with torch.no_grad():
                    for x, y in valid:
                        x, x_mask, y, y_mask = prepare_data(params, x, y)
                        # print('x',len(x))
                        # print('x','x_mask',x.shape,x_mask.shape) #(2, 1, 170, 710) (2, 170, 710) 2 是batch
                        # print('y,ymask',y.shape,y_mask.shape)  # y,ymask (22, 2) (22, 2)  2 是batch 

                        x = torch.from_numpy(x).cuda()
                        x_mask = torch.from_numpy(x_mask).cuda()
                        y = torch.from_numpy(y).cuda()
                        y_mask = torch.from_numpy(y_mask).cuda()

                        # permute for multi-GPU training
                        y = y.permute(1, 0)
                        y_mask = y_mask.permute(1, 0)

                        # forward
                        scores, alphas = WAP_model(params, x, x_mask, y, y_mask)

                        # print('score,alpha',scores.shape,alphas.shape)  # torch.Size([2, 22, 186]) torch.Size([2, 22, 11, 45])

                        
                        # recover from permute
                        alphas = alphas.permute(1, 0, 2, 3)
                        scores = scores.permute(1, 0, 2)
                        scores = scores.contiguous()
                        scores = scores.view(-1, scores.shape[2])
                        # print('score',scores.shape) # torch.Size([44, 186])

                        y = y.permute(1, 0)
                        y_mask = y_mask.permute(1, 0)
                        y = y.contiguous()
                        
                        loss = criterion(scores, y.view(-1))
                        # print('loss',loss.shape) # 44
                        loss = loss.view(y.shape[0], y.shape[1])
                        loss = (loss * y_mask).sum(0) / y_mask.sum(0)
                        # loss = ((loss * y_mask).sum(0)).mean()
                        loss = loss.mean()
                        loss_valid += loss.item()
                        valid_count_batch +=1
                        if valid_count_batch% 1000 ==0:
                            print('valid_id:',valid_count_batch, time.time()-valid_loss_start)
                            valid_loss_start = time.time()
                    # break
                        

                loss_valid /= len(valid)
                history_loss.append(loss_valid)
                print('validing__','id',uidx,'loss',loss_valid,'min_loss',np.array(history_loss).min())
                print('valid_loss_time',time.time()-valid_loss_start)


                #save_model
                if  loss_valid <= np.array(history_loss).min():
                    bad_counter = 0
                    print('Saving model params ... ')

                    if not os.path.exists(saveto):
                        os.mkdir(saveto)
                    if multi_gpu_flag:
                        torch.save(WAP_model.module.state_dict(), saveto+'WAP_params'+str(uidx)+'_lr'+str(lrate)+'.pkl')
                    else:
                        torch.save(WAP_model.state_dict(), saveto+'WAP_params'+str(uidx)+'_lr_'+str(lrate)+'.pkl')

                if loss_valid > np.array(history_loss).min():
                    bad_counter += 1
                    if bad_counter > patience:
                        #if halfLrFlag == 2:
                        if halfLrFlag == halfLrFlag_set:
                            print('Early Stop!')
                            estop = True
                            break
                        else:
                            print('Lr decay and retrain!')
                            bad_counter = 0
                            #lrate = lrate / 10.
                            lrate = lrate / lr_decrease_rate
                            for param_group in optimizer.param_groups:
                                param_group['lr'] = lrate
                            halfLrFlag += 1

                # print('valid_over__','spend_time',time.time()-ud_start)  

        # validation
        # print('validataion')
        valid_stop = False
        valid_sample_time = time.time()
        if np.mod(uidx, validFreq) == 0:
            WAP_model.eval()
            
            with torch.no_grad():
                fpp_sample = open(valid_output[0], 'w')
                valid_count_idx = 0
                for x, y in valid:
                    for xx in x:
                        xx_pad = xx.astype(np.float32) / 255.
                        xx_pad = torch.from_numpy(xx_pad[None, :, :, :]).cuda()  # (1,1,H,W)
                        sample, score = gen_sample(WAP_model, xx_pad, params, multi_gpu_flag, k=10, maxlen=1000)
                        if len(score) == 0:
                            print('valid decode error happens')
                            valid_stop = True
                            break
                        score = score / np.array([len(s) for s in sample])
                        ss = sample[score.argmin()]
                        # write decoding results
                        fpp_sample.write(valid_uid_list[valid_count_idx])
                        valid_count_idx = valid_count_idx + 1
                        # symbols (without <eos>)
                        for vv in ss:
                            if vv == 0:  # <eos>
                                break
                            fpp_sample.write(' ' + worddicts_r[vv])
                        fpp_sample.write('\n')
                        # if valid_count_idx % 100==0:
                        #     valid_stop =True
                        #     break
                    if valid_stop:
                        break
            fpp_sample.close()
            print('valid set decode done','valid_number:',valid_count_idx)
            


        valid_stop = False

        # calculate wer and expRate
        if np.mod(uidx, validFreq) == 0 and valid_stop == False:
            os.system('python compute-wer.py ' + valid_output[0] + ' ' + valid_datasets[
                1] + ' ' + valid_result[0])

            fpp = open(valid_result[0])
            stuff = fpp.readlines()
            fpp.close()
            m = re.search('WER (.*)\n', stuff[0])
            valid_err = 100. * float(m.group(1))
            m = re.search('ExpRate (.*)\n', stuff[1])
            valid_sacc = 100. * float(m.group(1))
            history_errs.append(valid_err)

            # # the first time validation or better model
            # if uidx // validFreq == 0 or valid_err <= np.array(history_errs).min():
            #     bad_counter = 0
            #     print('Saving model params ... ')
            #     if multi_gpu_flag:
            #         torch.save(WAP_model.module.state_dict(), saveto)
            #     else:
            #         torch.save(WAP_model.state_dict(), saveto)

            # # worse model
            # if uidx / validFreq != 0 and valid_err > np.array(history_errs).min():
            #     bad_counter += 1
            #     if bad_counter > patience:
            #         if halfLrFlag == 2:
            #             print('Early Stop!')
            #             estop = True
            #             break
            #         else:
            #             print('Lr decay and retrain!')
            #             bad_counter = 0
            #             lrate = lrate / 10.
            #             for param_group in optimizer.param_groups:
            #                 param_group['lr'] = lrate
            #             halfLrFlag += 1
            if valid_err<min_Valid_WER:
                min_Valid_WER = valid_err
            if valid_sacc>max_ExpRate:
                max_ExpRate = valid_sacc
            print('Valid WER: %.2f%%, ExpRate: %.2f%%' % (valid_err, valid_sacc),'min Valid WER: %.2f%%, max ExpRate: %.2f%%' % (min_Valid_WER, max_ExpRate))
            print('valid_sample_time',time.time()-valid_sample_time)
            ud_epoch = (time.time() - ud_epoch) / 60.
            print('epoch_toal_cost time ... minute', ud_epoch)

        # finish after these many updates
        if uidx >= finish_after:
            print('Finishing after %d iterations!' % uidx)
            estop = True
            break

    print('Seen %d samples' % n_samples)

    # early stop
    if estop:
        break
