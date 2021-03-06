# -*- coding: utf-8 -*-

import numpy as np
#import matplotlib.pyplot as plt
from sklearn.metrics import auc, roc_curve
from graphnnSiamese import graphnn
import json

def get_f_name(DATA, SF, CM, OP, VS):
    F_NAME = []
    for sf in SF:
        for cm in CM:
            for op in OP:
                for vs in VS:
                    F_NAME.append(DATA+sf+cm+op+vs+".json")
    return F_NAME


def get_f_dict(F_NAME):
    name_num = 0
    name_dict = {}
    for f_name in F_NAME:
        with open(f_name) as inf:
            for line in inf:
                g_info = json.loads(line.strip())
                if (g_info['fname'] not in name_dict):
                    name_dict[g_info['fname']] = name_num
                    name_num += 1
    return name_dict

class graph(object):
    def __init__(self, node_num = 0, label = None, name = None):
        self.node_num = node_num
        self.label = label
        self.name = name
        self.features = []
        self.succs = []
        self.preds = []
        if (node_num > 0):
            for i in range(node_num):
                self.features.append([])
                self.succs.append([])
                self.preds.append([])
                
    def add_node(self, feature = []):
        self.node_num += 1
        self.features.append(feature)
        self.succs.append([])
        self.preds.append([])
        
    def add_edge(self, u, v):

        self.succs[u].append(v)
        self.preds[v].append(u)

    def toString(self):
        ret = '{} {}\n'.format(self.node_num, self.label)
        for u in range(self.node_num):
            for fea in self.features[u]:
                ret += '{} '.format(fea)
            ret += str(len(self.succs[u]))
            for succ in self.succs[u]:
                ret += ' {}'.format(succ)
            ret += '\n'
        return ret

        
def read_graph(F_NAME, FUNC_NAME_DICT, FEATURE_DIM):
    graphs = []
    classes = []
    if FUNC_NAME_DICT != None:
      
        for f in range(len(FUNC_NAME_DICT)):
            classes.append([])

    for f_name in F_NAME:
        with open(f_name) as inf:
            for line in inf:

                g_info = json.loads(line.strip())
                # label表示每一个函数出现的次序
                label = FUNC_NAME_DICT[g_info['fname']]
                # classes数组的下标对应一个函数，下标即是次序
                # 数组中的每一个元素对应的数组是该函数的不同平台编译的ACFG图的ID
                classes[label].append(len(graphs))
                # cur_graph存储顶点以及顶点之间边的信息
                cur_graph = graph(g_info['n_num'], label, g_info['src'])
                for u in range(g_info['n_num']):
                    cur_graph.features[u] = np.array(g_info['features'][u])
                    for v in g_info['succs'][u]:
                        cur_graph.add_edge(u, v)
                graphs.append(cur_graph)

    return graphs, classes


def partition_data(Gs, classes, partitions, perm):
    C = len(classes)
    st = 0.0
    ret = []
    for part in partitions:
        cur_g = []
        cur_c = []
        ed = st + part * C
        for cls in range(int(st), int(ed)):
            prev_class = classes[perm[cls]]
            cur_c.append([])
            for i in range(len(prev_class)):
                cur_g.append(Gs[prev_class[i]])
                cur_g[-1].label = len(cur_c)-1
                cur_c[-1].append(len(cur_g)-1)

        ret.append(cur_g)
        ret.append(cur_c)
        st = ed

    return ret


def generate_epoch_pair(Gs, classes, M, output_id = False, load_id = None):
    epoch_data = []
    id_data = []   # [ ([(G0,G1),(G0,G1), ...], [(G0,H0),(G0,H0), ...]), ... ]
    if load_id is None:
        st = 0
        while st < len(Gs):
            if output_id:
                X1, X2, m1, m2, y, pos_id, neg_id = get_pair(Gs, classes,
                        M, st=st, output_id=True)
                id_data.append( (pos_id, neg_id) )
            else:
                X1, X2, m1, m2, y = get_pair(Gs, classes, M, st=st)
            epoch_data.append( (X1,X2,m1,m2,y) )
            st += M
    else:   ## Load from previous id data
        id_data = load_id
        for id_pair in id_data:
            X1, X2, m1, m2, y = get_pair(Gs, classes, M, load_id=id_pair)
            epoch_data.append( (X1, X2, m1, m2, y) )

    if output_id:
        return epoch_data, id_data
    else:
        return epoch_data


def get_pair(Gs, classes, M, st = -1, output_id = False, load_id = None):
    if load_id is None:
        # 所有函数的数量
        C = len(classes)

        if (st + M > len(Gs)):
            M = len(Gs) - st
        ed = st + M
        # 正样本对
        pos_ids = [] # [(G_0, G_1)]
        neg_ids = [] # [(G_0, H_0)]

        for g_id in range(st, ed):
            g0 = Gs[g_id]
            # cls代表g0代表的函数的次序
            cls = g0.label
            # tot_g表示该函数对应的ACFGS的个数
            tot_g = len(classes[cls])
            if (len(classes[cls]) >= 2):
                g1_id = classes[cls][np.random.randint(tot_g)]
                while g_id == g1_id:
                    g1_id = classes[cls][np.random.randint(tot_g)]
                pos_ids.append( (g_id, g1_id) )

            cls2 = np.random.randint(C)
            while (len(classes[cls2]) == 0) or (cls2 == cls):
                cls2 = np.random.randint(C)

            tot_g2 = len(classes[cls2])
            h_id = classes[cls2][np.random.randint(tot_g2)]
            neg_ids.append( (g_id, h_id) )
    else:
        # 正反例集合
        pos_ids = load_id[0]
        neg_ids = load_id[1]

     # 正例和反例的个数
    M_pos = len(pos_ids)

    M_neg = len(neg_ids)

    # 两个集合的总长度为M
    M = M_pos + M_neg

    maxN1 = 0
    maxN2 = 0 #870
    for pair in pos_ids:
        # 取正例ACFG图的顶点数目的最大值
        maxN1 = max(maxN1, Gs[pair[0]].node_num)
        maxN2 = max(maxN2, Gs[pair[1]].node_num)
    for pair in neg_ids:

        maxN1 = max(maxN1, Gs[pair[0]].node_num)
        maxN2 = max(maxN2, Gs[pair[1]].node_num)

    feature_dim = len(Gs[0].features[0])
    # 一共十对数据，其中左边十个输入作为第一个网络的输入
    # 右边十个数据作为第二个网络的输入
    X1_input = np.zeros((M, maxN1, feature_dim))
    X2_input = np.zeros((M, maxN2, feature_dim))
    node1_mask = np.zeros((M, maxN1, maxN1))
    node2_mask = np.zeros((M, maxN2, maxN2))
    # y为标签
    y_input = np.zeros((M))
    
    for i in range(M_pos):
        y_input[i] = 1
        # 找到两个index对应的图
        g1 = Gs[pos_ids[i][0]]
        g2 = Gs[pos_ids[i][1]]
        for u in range(g1.node_num):
            # X1的每一行代表着一个图
            X1_input[i, u, :] = np.array( g1.features[u] )
            for v in g1.succs[u]:
                node1_mask[i, u, v] = 1
        for u in range(g2.node_num):
            X2_input[i, u, :] = np.array( g2.features[u] )
            for v in g2.succs[u]:
                node2_mask[i, u, v] = 1
        
    for i in range(M_pos, M_pos + M_neg):
        y_input[i] = -1
        g1 = Gs[neg_ids[i-M_pos][0]]
        g2 = Gs[neg_ids[i-M_pos][1]]
        for u in range(g1.node_num):
            X1_input[i, u, :] = np.array( g1.features[u] )
            for v in g1.succs[u]:
                node1_mask[i, u, v] = 1
        for u in range(g2.node_num):
            X2_input[i, u, :] = np.array( g2.features[u] )
            for v in g2.succs[u]:
                node2_mask[i, u, v] = 1
    if output_id:
        return X1_input,X2_input,node1_mask,node2_mask,y_input,pos_ids,neg_ids
    else:
        return X1_input,X2_input,node1_mask,node2_mask,y_input


def train_epoch(model, graphs, classes, batch_size, load_data=None):
    if load_data is None:
        epoch_data = generate_epoch_pair(graphs, classes, batch_size)
    else:
        epoch_data = load_data

    perm = np.random.permutation(len(epoch_data))   #Random shuffle

    cum_loss = 0.0
    for index in perm:
        cur_data = epoch_data[index]
        X1, X2, mask1, mask2, y = cur_data
        # mask 代表图的连接情况
        loss = model.train(X1, X2, mask1, mask2, y)
        cum_loss += loss

    return cum_loss / len(perm)

# 输出每一个epoch后的auc值
def  get_auc_epoch(model, graphs, classes, batch_size, load_data=None):
    tot_diff = []
    tot_truth = []
    sum = 0
    posNum = 0
    pos1Num = 0
    if load_data is None:
        epoch_data= generate_epoch_pair(graphs, classes, batch_size)
    else:
        epoch_data = load_data

    i = 0
    for cur_data in epoch_data:
        X1, X2, m1, m2,y  = cur_data
        diff = model.calc_diff(X1, X2, m1, m2)
        #验证性能时打印的输出
        Len = len(diff)
        while(i < Len):
            if(diff[i] * y[i] < 0):
                posNum += 1
                if(diff[i] < 0 and y[i] > 0):
                    pos1Num += 1
            i += 1
        #print -diff
        i = 0
        #print y
        sum += Len
        tot_diff += list(diff)
        tot_truth += list(y > 0)


    diff = np.array(tot_diff)
    truth = np.array(tot_truth)

    fpr, tpr, thres = roc_curve(truth, (1-diff)/2)
    model_auc = auc(fpr, tpr)
    posACu = posNum / float(sum)
    pos1Acu = (pos1Num * 2) / float(sum)
    return model_auc, fpr, tpr, thres, posACu, pos1Acu
