# -*- coding: utf-8 -*-
import tensorflow as tf
#import matplotlib.pyplot as plt
import numpy as np
import datetime
from sklearn.metrics import roc_auc_score


def graph_embed(X, msg_mask, N_x, N_embed, N_o, iter_level, Wnode, Wembed, W_output, b_output, cell):
    #X -- affine(W1) -- ReLU -- (Message -- affine(W2) -- add (with aff W1)
    # -- ReLU -- )* MessageAll  --  output
    # 每个ACFGS图的每一个顶点向量与Wnode权重矩阵相乘，得到 一个三维的矩阵node_val
    node_val = tf.reshape(tf.matmul( tf.reshape(X, [-1, N_x]) , Wnode),
            [tf.shape(X)[0], -1, N_embed])
    # 相当于第0次迭代的嵌入
    cur_msg = tf.nn.relu(node_val)   #[batch, node_num, embed_dim]
    for t in range(iter_level):
        #Message convey
        # Li_t是一个矩阵，表示与当前节点相关联的嵌入
        Li_t = tf.matmul(msg_mask, cur_msg)  #[batch, node_num, embed_dim]
        #Complex Function
        cur_info = tf.reshape(Li_t, [-1, N_embed])
        # 此for循环指嵌入深度为2的那两层
        for Wi in Wembed:
            if (Wi == Wembed[-1]):
                # 这里的wi指的是pi
                cur_info = tf.matmul(cur_info, Wi)
            else:
                cur_info = tf.nn.relu(tf.matmul(cur_info, Wi))
        # 学习邻接边的结果
        neigh_val_t = tf.reshape(cur_info, tf.shape(Li_t))
        #Adding
        tot_val_t = node_val + neigh_val_t
        #Nonlinearity
        # tot_msg_t表示第i次迭代的嵌入
        tot_msg_t = tf.nn.tanh(tot_val_t)
        # 一个矩阵，元素代表每一个ACFGS图的每个顶点在第i次迭代中的嵌入
        cur_msg = tot_msg_t   #[batch, node_num, embed_dim]


    # 按行求和
    #g_embed = tf.reduce_sum(cur_msg, 1)   #[batch, embed_dim]

    outputs, last_states = tf.nn.dynamic_rnn(
        cell=cell,
        dtype=tf.float32,
        inputs=cur_msg)

    # 最后输出又是一层
    output = tf.matmul(last_states, W_output) + b_output

    # 返回一个数组，元素为Batch中每一个ACFGS图的嵌入
    return output


class graphnn(object):
    def __init__(self,
                    N_x, # 图节点的特征维度 7
                    Dtype, # 浮点型 float
                    N_embed,# 嵌入维度 64
                    depth_embed, # 嵌入深度 2
                    N_o, # 输出向量维度
                    ITER_LEVEL, # 迭代次数
                    lr,
                    device = '/gpu:0'
                ):

        self.NODE_LABEL_DIM = N_x

        tf.reset_default_graph()
        with tf.device(device):
            Wnode = tf.Variable(tf.truncated_normal(
                shape = [N_x, N_embed], stddev = 0.1, dtype = Dtype))
            Wembed = []
            for i in range(depth_embed):
                Wembed.append(tf.Variable(tf.truncated_normal(
                    shape = [N_embed, N_embed], stddev = 0.1, dtype = Dtype)))

            W_output = tf.Variable(tf.truncated_normal(
                shape = [N_embed, N_o], stddev = 0.1, dtype = Dtype))
            b_output = tf.Variable(tf.constant(0, shape = [N_o], dtype = Dtype))

            # 输入数据：ACFGS图的顶点信息
            X1 = tf.placeholder(Dtype, [None, None, N_x]) #[B, N_node, N_x]
            # 输入数据：图的边信息
            msg1_mask = tf.placeholder(Dtype, [None, None, None])
                                            #[B, N_node, N_node]
            self.X1 = X1
            self.msg1_mask = msg1_mask
            # 在整个训练网络中加入G一层RU网络
            rnn_hidden_size = 64
            cell = tf.contrib.rnn.GRUCell(num_units=rnn_hidden_size)
            self.cell = cell

            # 一个数组，十个元素，表示十个ACFGS图的嵌入
            embed1 = graph_embed(X1, msg1_mask, N_x, N_embed, N_o, ITER_LEVEL,
                    Wnode, Wembed, W_output, b_output, self.cell)  #[B, N_x]

            X2 = tf.placeholder(Dtype, [None, None, N_x])
            msg2_mask = tf.placeholder(Dtype, [None, None, None])
            self.X2 = X2
            self.msg2_mask = msg2_mask
            embed2 = graph_embed(X2, msg2_mask, N_x, N_embed, N_o, ITER_LEVEL,
                    Wnode, Wembed, W_output, b_output, self.cell)

            label = tf.placeholder(Dtype, [None, ]) #same: 1; different:-1
            self.label = label
            self.embed1 = embed1

            # cos是一个数组，十个元素，表示各对ACFGS图余弦相似度
            cos = tf.reduce_sum(embed1*embed2, 1) / tf.sqrt(tf.reduce_sum(
                embed1**2, 1) * tf.reduce_sum(embed2**2, 1) + 1e-10)

            diff = -cos
            self.diff = diff
            loss = tf.reduce_mean( (diff + label) ** 2 )
            self.loss = loss

            optimizer = tf.train.AdamOptimizer(learning_rate=lr).minimize(loss)
            self.optimizer = optimizer


    
    def say(self, string):
        print string
        if self.log_file != None:
            self.log_file.write(string+'\n')
    
    def init(self, LOAD_PATH, LOG_PATH):
        config = tf.ConfigProto()
        config.gpu_options.allow_growth = True
        sess = tf.Session(config=config)
        saver = tf.train.Saver()
        self.sess = sess
        self.saver = saver
        self.log_file = None
        if (LOAD_PATH is not None):
            if LOAD_PATH == '#LATEST#':
                checkpoint_path = tf.train.latest_checkpoint('./')
            else:
                checkpoint_path = LOAD_PATH
            saver.restore(sess, checkpoint_path)
            if LOG_PATH != None:
                self.log_file = open(LOG_PATH, 'a+')
            self.say('{}, model loaded from file: {}'.format(
                datetime.datetime.now(), checkpoint_path))
        else:
            sess.run(tf.global_variables_initializer())
            if LOG_PATH != None:
                self.log_file = open(LOG_PATH, 'w')
            self.say('Training start @ {}'.format(datetime.datetime.now()))
    
    def get_embed(self, X1, mask1):
        vec, = self.sess.run(fetches=[self.embed1],
                feed_dict={self.X1:X1, self.msg1_mask:mask1})
        return vec

    def calc_loss(self, X1, X2, mask1, mask2, y):
        cur_loss, = self.sess.run(fetches=[self.loss], feed_dict={self.X1:X1,
            self.X2:X2,self.msg1_mask:mask1,self.msg2_mask:mask2,self.label:y})
        return cur_loss
        
    def calc_diff(self, X1, X2, mask1, mask2):
        diff, = self.sess.run(fetches=[self.diff], feed_dict={self.X1:X1,
            self.X2:X2, self.msg1_mask:mask1, self.msg2_mask:mask2})
        return diff
    
    def train(self, X1, X2, mask1, mask2, y):
        loss,_ = self.sess.run([self.loss,self.optimizer],feed_dict={self.X1:X1,
            self.X2:X2,self.msg1_mask:mask1,self.msg2_mask:mask2,self.label:y})
        return loss
    
    def save(self, path, epoch=None):
        checkpoint_path = self.saver.save(self.sess, path, global_step=epoch)
        return checkpoint_path
