#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os.path

import gunicorn

from ai import AI
from config import Config
from contents import get_contents
from storage import Storage
from flask import Flask, jsonify, request, make_response

app = Flask(__name__)


@app.route('/process', methods=['POST'])
def run():
    url = request.form['input_file_path']
    filename = request.form['out_file_name']
    appKey = request.form['app_key']
    try:

        """Run the application."""
        cfg = Config()
        cfg.open_ai_key = appKey
        ai = AI(cfg)

        if os.path.exists(filename + '.bin') and os.path.exists(filename + '.csv'):
            print('文件已存在')
            return ""
        else:
            contents, lang = get_contents(url)
            print("文章已抓取，片段数量：", len(contents))
            for content in contents:
                print('\t', content)
            # 1. 对文章的每个段落生成embedding
            embeddings, tokens = ai.create_embeddings(contents)
            print("已创建嵌入，嵌入数量：", len(embeddings), "，使用的令牌数：", tokens, "，花费：",
                  tokens / 1000 * 0.0004,
                  "美元")
            storage = Storage.create_storage(cfg, filename=filename)
            storage.clear(filename)
            storage.add_all(embeddings, filename)
            print("已存储嵌入")
            print("=====================================")
            # 2. 生成embedding式摘要，有基于SIF的加权平均和一般的直接求平均，懒得中文分词了这里使用的是直接求平均，英文可以改成SIF
            print("=====================================")
            # res = ai.generate_summary(embeddings, num_candidates=100,
            #                           use_sif=lang not in ['zh', 'ja', 'ko', 'hi', 'ar', 'fa'])
            return str(tokens) # 将 tokens 转换为字符串类型，并将其作为响应返回

    except Exception as e:
        print("Error:", e)
        return 'fail'


@app.route('/delete', methods=['DELETE'])
def delete():
    cfg = Config()
    filename = request.form['out_file_name']
    storage = Storage.create_storage(cfg, filename=filename)
    storage.clear(filename)
    return "success"


@app.route('/ask', methods=['POST'])
def ask():
    # 获取请求中的参数
    query = request.form['query']
    filename = request.form['out_file_name']
    appKey = request.form['app_key']

    cfg = Config()
    cfg.open_ai_key = appKey
    ai = AI(cfg)
    if os.path.exists(filename + '.bin') and os.path.exists(filename + '.csv'):
        storage = Storage.create_storage(cfg, filename=filename)
        # 1. 对问题生成embedding
        embedding = ai.create_embedding(query)
        # 2. 从数据库中找到最相似的片段
        texts = storage.get_texts(embedding[1])
        print("已找到相关片段（前5个）：")
        for text in texts[:5]:
            print('\t', text)
        # 3. 把相关片段推给AI，AI会根据这些片段回答问题
        res, token = ai.completion(query, texts)
        print("=====================================")
        return jsonify({'answer': res, 'token': token})
    else:
        response = make_response('docId not found')
        response.status_code = 404
        return response


@app.route("/")
def init():
    '''
    初始化启动接口
    http://localhost:5000/
    '''
    return u"gunicorn+flask web服务正常启动........"


if __name__ == '__main__':
    app.run()
    # gunicorn_app = gunicorn.app.base.BaseApplication()
    # gunicorn_app.app = app
    # gunicorn_app.run()
    # gunicorn_app.run(bind='0.0.0.0:5174')
