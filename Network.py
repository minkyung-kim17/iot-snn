
import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
from torch.nn.utils.rnn import pack_padded_sequence, pad_packed_sequence
import numpy as np
import pdb


class SSIM(nn.Module):
    def __init__(self, input_size, enc_hid_size, dec_hid_size, output_size):
        super(SSIM, self).__init__()

        self.input_size = input_size
        self.enc_hid_size = enc_hid_size  # size of hidden state at Encoder
        self.dec_hid_size = dec_hid_size  # size of hidden state at Decoder
        self.output_size = output_size

        self.enc_layer = 2
        self.dec_layer = 2

        self.dropout = 0.2

        self.encoder = nn.LSTM(self.input_size, self.enc_hid_size,
                               num_layers=self.enc_layer, batch_first=True,
                               dropout=self.dropout, bidirectional=True)
        self.attn = nn.Linear(self.dec_hid_size + self.enc_hid_size * 2,
                                   self.dec_hid_size)
        self.v = nn.Parameter(torch.rand(self.dec_hid_size))
        self.decoder = nn.LSTM(self.enc_hid_size * 2 + self.output_size, self.dec_hid_size,
                               num_layers=self.dec_layer, batch_first=True,
                               dropout=self.dropout)
        self.linear = nn.Linear(self.enc_hid_size * 2 + self.dec_hid_size,
                                self.output_size)

    def forward(self, input):
        if isinstance(input, torch.nn.utils.rnn.PackedSequence):
            ''' encoder '''
            packed_output, (enc_h, enc_c) = self.encoder(input)
            encoder_outputs, input_lengths = pad_packed_sequence(packed_output, batch_first=True)

            batch_size = encoder_outputs.size(0)
            src_len = encoder_outputs.size(1)

            output = torch.zeros(batch_size, self.output_size)

            ''' decoder with attention '''
            dec_h0 = torch.randn(self.dec_layer, batch_size, self.dec_hid_size)
            dec_c0 = torch.randn(self.dec_layer, batch_size, self.dec_hid_size)

            y0 = torch.zeros(self.output_size).repeat(batch_size)  # ?????

            hidden = dec_h0

            y = y0.unsqueeze(1)
            for i in range(src_len):
                ''' attention '''
                hidden = torch.unbind(hidden, dim=0)[0]  # 마지막 layer가 [0]이 맞나?
                hidden = hidden.unsqueeze(1).repeat(1, src_len, 1)

                attentions = torch.zeros(1, src_len)
                for batch_idx, input_length in enumerate(input_lengths):
                    energy = torch.tanh(self.attn(torch.cat((hidden[batch_idx, :input_length, :], encoder_outputs[batch_idx, :input_length, :]), dim=1)))
                    energy = energy.permute(1, 0)

                    attention = self.v.unsqueeze(0).mm(energy)
                    attention = F.softmax(attention, dim=1)
                    attention = torch.cat((attention, torch.zeros(src_len - input_length).unsqueeze(0)), dim=1)

                    attentions = torch.cat((attentions, attention), dim=0)
                attention = attentions[1:, :].unsqueeze(2).repeat(1, 1, self.enc_hid_size * 2)

                ''' context '''
                context = attention * encoder_outputs
                context = torch.sum(context, dim=1)  # 각 input의 유효 sequence 길이 만큼의 h_i만 weighted sum

                ''' decoder lstm '''
                dec_input = torch.cat((y, context), dim=1)

                decoder_outputs, (dec_h, dec_c) = self.decoder(dec_input.unsqueeze(1), (dec_h0, dec_c0))

                ''' dense layer '''
                lin_input = torch.cat((decoder_outputs.squeeze(), context), dim=1)

                y = self.linear(lin_input)
                output = torch.cat((output, y), dim=1)

                hidden = decoder_outputs.permute(1, 0, 2)

        else:
            batch_size = input.size(0)
            src_len = input.size(1)

            output = torch.zeros(batch_size, self.output_size)

            ''' encoder '''
            enc_h0 = torch.randn(self.enc_layer * 2, batch_size, self.enc_hid_size)  # 2 for bi-LSTM
            enc_c0 = torch.randn(self.enc_layer * 2, batch_size, self.enc_hid_size)

            encoder_outputs, (enc_h, enc_c) = self.encoder(input, (enc_h0, enc_c0))

            ''' decoder with attention '''
            dec_h0 = torch.randn(self.dec_layer, batch_size, self.dec_hid_size)
            dec_c0 = torch.randn(self.dec_layer, batch_size, self.dec_hid_size)

            y0 = torch.zeros(self.output_size).repeat(batch_size)  # ?????

            hidden = dec_h0
            y = y0.unsqueeze(1)  # output dimension이 달라지면, unsqueeze 확인!
            for i in range(src_len):
                ''' attention '''
                hidden = torch.unbind(hidden, dim=0)[0]
                hidden = hidden.unsqueeze(1).repeat(1, src_len, 1)

                energy = torch.tanh(self.attn(torch.cat((hidden, encoder_outputs), dim=2)))
                energy = energy.permute(0, 2, 1)

                v = self.v.repeat(batch_size, 1).unsqueeze(1)

                attention = torch.bmm(v, energy).squeeze(1)
                attention = F.softmax(attention, dim=1)

                attention = attention.unsqueeze(2).repeat(1, 1, self.enc_hid_size * 2)

                ''' context '''
                context = attention * encoder_outputs
                context = torch.sum(context, dim=1)  # 각 input의 유효 sequence 길이 만큼의 h_i만 weighted sum

                ''' decoder lstm '''
                dec_input = torch.cat((y, context), dim=1)

                decoder_outputs, (dec_h, dec_c) = self.decoder(dec_input.unsqueeze(1), (dec_h0, dec_c0))

                ''' dense layer '''
                lin_input = torch.cat((decoder_outputs.squeeze(), context), dim=1)

                y = self.linear(lin_input)
                output = torch.cat((output, y), dim=1)

                hidden = decoder_outputs.permute(1, 0, 2)

        return output[:, 1:]
