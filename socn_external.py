from pyquery import PyQuery as pq

def get_article(html, base):
    rt = pq(html)
    id = base.split('/')[-1]
    title = rt('.fs-headline1').eq(0).text().strip()
    ques_cont = rt('.question .js-post-body').html()
    ques_vote = rt('.question .js-vote-count').text().strip()
    tags = [pq(el).text().strip() for el in rt('.question a.post-tag')]
    tags = ', '.join(tags)
    ques_time = rt('#question-header~div time').text().strip()
    el_answers = rt('.answer')
    answers = [
        {
            'cont': pq(el).find('.js-post-body').html(),
            'vote': pq(el).find('.js-vote-count').text().strip(),
            'time': pq(el).find('.user-action-time').text().strip().split(' ')[1],
        
        }
        for el in el_answers
    ]
    
    cont = f'''
        <blockquote>
        <p>ID：{id}</p>
        <p>赞同：{ques_vote}</p>
        <p>时间：{ques_time}</p>
        <p>标签：{tags}</p>
        </blockquote>
        {ques_cont}
    ''' + '\n'.join([
        f'''
            <hr />
            <h2>回答 #{i}</h2>
            <blockquote>
            <p>赞同：{ans["vote"]}</p>
            <p>时间：{ans["time"]}</p>
            </blockquote>
            {ans["cont"]}
        '''
        for i, ans in enumerate(answers, 1)
    ])
    
    return {
        'title': title,
        'content': cont,
    }
    