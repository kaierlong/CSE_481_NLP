import re
import json
import codecs
import pickle
import operator
import random
import lcmc_queries as lcmc
import pinyin_util as pu

# total size of lines to read from txt file
# used only for debugging purpose
MAX_LINE_NUMBER = 3

# probability to generate an abbreviation tuple
GENERATE_ABBREVIATION_TUPLE_PROBABILITY = 0.5
# probability to use abbreviation for a given
# pinyin token
GENERATE_ABBREVIATION_TOKEN_PROBABILITY = 0.5

def build_parallel_paragraphs_lcmc():
    # each paragraph[0] = "^" as START symbol
    char_paragraphs = []
    pinyin_paragraphs = []

    for tup in lcmc.get_char_paragraphs():
        char_paragraphs.append(list(tup[0]))

    for tup in lcmc.get_pinyin_paragraphs():
        # drop tunes and add paddings
        p = re.sub(r'([a-z]+)[0-9] *', r' \1 ', tup[0])
        p = re.sub(r'([^a-z ])', r' \1 ', p)
        # fix "uu"=>"v" in lcmc pinyin
        p = re.sub(r'uu', r'v', p)        
        pinyin_paragraphs.append(p.split())

    assert len(char_paragraphs) == len(pinyin_paragraphs)
    return list(zip(char_paragraphs, pinyin_paragraphs))


def build_parallel_paragraphs_from_txt(filename, debug = False):
    # each paragraph[0] = "^" as START symbol
    char_paragraphs = []
    pinyin_paragraphs = []

    with codecs.open(filename, encoding='utf-8') as f:
        lines = f.readlines()

    if (debug):
        lines = lines[0:MAX_LINE_NUMBER]

    lines = [x.strip() for x in lines]
    lines = list(set(lines))
    
    for i in range(len(lines)):
        parts = lines[i].split(' ==> ')
        p = re.sub(r'([^a-z ])', r' \1 ', "^" + parts[1])
        char_paragraphs.append(list("^" + parts[0]))
        pinyin_paragraphs.append(p.split())
    return list(zip(char_paragraphs, pinyin_paragraphs))

    
# min_paragraph_len includes "^"
# first_n: only extract the first n triples
def extract_triples(paragraph_pairs, context_window=10, max_input_window=5, first_n=None, min_paragraph_len=6):
    # print(len(paragraph_pairs))
    # triples[i] = (context, pinyins, chars)
    triples = []
    all_valid_chars = pu.get_all_candidates_chars()

    for pp in paragraph_pairs:
        if len(pp[0]) != len(pp[1]):
            # print(''.join(pp[0]) + " ==> " + ' '.join(pp[1]))
            # weird encoding error in the dataset, skip
            continue
        if len(pp[0]) < min_paragraph_len:
            continue

        # TODO: Consider only putting cursor and input window on word boundaries
        for cursor in range(1, len(pp[0])):
            for input_window_end in range(cursor + 1, min(cursor + max_input_window + 1, len(pp[0]))):
                if len([i for i in range(cursor, input_window_end) if not pp[0][i] in all_valid_chars]) > 0:
                    break
                context = pp[0][max(0, cursor - context_window):cursor]
                pinyins = pp[1][cursor:input_window_end]
                print(pinyins)
                chars = pp[0][cursor:input_window_end]

                if (len(chars) > 0):
                    triples.append((" ".join(context), " ".join(pinyins), " ".join(chars)))
                    if first_n is not None and len(triples) == first_n:
                        return triples
                    if (random.random() < GENERATE_ABBREVIATION_TUPLE_PROBABILITY):
                        # print("in generating abbreviation tuple case")
                        abbreviation_pinyins = generate_abbreviation_noise(pinyins, GENERATE_ABBREVIATION_TOKEN_PROBABILITY)
                        if (abbreviation_pinyins):
                            triples.append((" ".join(context), " ".join(abbreviation_pinyins), " ".join(chars)))
    print(len(triples))
    return triples

def generate_abbreviation_noise(pinyins, prob):
    """
    make a noisy copy of the original pinyin tokens
    such that each pinyin token has 'prob' probability
    of being replaced by its abbreviation.

    Note: This function guaranteens that when combining
    all the tokens in the result array and then splitting
    it again using segment_with_hint() function in pinyin_uitl.py,
    the size of the array after splitting is the same as the original
    'pinyins' array. 
    i.e. the situation where the pinyins array is
    ["tian", "an", "men"] and the result array is
    ["t", "a", "m"] is not possible since when combining
    "t" with "a", it forms a valid pinyin token "ta"; thus when
    splitting the pinyin string "tam", it will be splitted into
    ["ta", "m"], which is shorter than the original array.
    """
    results = []
    for pinyin_token in pinyins:
        abbreviation = pinyin_token[0:2]
        if (abbreviation != "zh" 
            and abbreviation != "ch" 
            and abbreviation != "sh"):
            abbreviation = pinyin_token[0]
        results.append(abbreviation)

    for i in range(0, len(results)):
        if (random.random() > prob):
            results[i] = pinyins[i]

    # print("orignal array:", pinyins)
    # print("abbreviation array:", results)
    segment_results_result = pu.segment_with_hint("".join(results))
    segment_original_result = pu.segment_with_hint("".join(pinyins))
    
    # print("segmentation result for noisy result:", segment_results_result)
    # print("segmentation result for orignal array:", segment_original_result)
    if (len(segment_results_result) == len(segment_original_result)):
        print("returning result")
        return results
    else:
        # print("returning None due to length inconsistency")
        return None

def generate_typo_noise(pinyins):
    return 0

def gen_vocab(raw_file, filename):
    with codecs.open(raw_file, encoding='utf-8') as f:
        lines = f.readlines()
    lines = [line.strip() for line in lines]
    c = {}
    for line in lines:
        tokens = list(line)
        for token in tokens:
            if not token in c:
                c[token] = 0
            c[token] = c[token] + 1

    with codecs.open(filename, 'w', encoding='utf-8') as fout:
        for k in sorted(c.keys()):
            fout.write(k + "\t" + str(c[k]) + "\n")

def gen_source_target_files(triples, filename):
    n = len(triples)
    train_size = int(n * .7)
    dev_size = int(n * .1)
    test_size = n - train_size - dev_size
    print("train: " + str(train_size))
    print("dev: " + str(dev_size))
    print("test: " + str(test_size))

    with codecs.open("data/train/" + filename + ".source", 'w', encoding='utf-8') as train_source:
        with codecs.open("data/train/" + filename + ".target", 'w', encoding='utf-8') as train_target:
            with codecs.open("data/dev/" + filename + ".source", 'w', encoding='utf-8') as dev_source:
                with codecs.open("data/dev/" + filename + ".target", 'w', encoding='utf-8') as dev_target:
                    with codecs.open("data/test/" + filename + ".source", 'w', encoding='utf-8') as test_source:
                        with codecs.open("data/test/" + filename + ".target", 'w', encoding='utf-8') as test_target:
                            
                            for tup in triples[:train_size]:
                                train_source.write(tup[0] + " | " + " ".join(list("".join(tup[1].split(" ")))) + "\n")
                                train_target.write(tup[2] + "\n")
                            
                            for tup in triples[train_size:train_size + dev_size]:
                                dev_source.write(tup[0] + " | " + " ".join(list("".join(tup[1].split(" ")))) + "\n")
                                dev_target.write(tup[2] + "\n")
                            
                            for tup in triples[train_size + dev_size:]:
                                test_source.write(tup[0] + " | " + " ".join(list("".join(tup[1].split(" ")))) + "\n")
                                test_target.write(tup[2] + "\n")

if __name__ == "__main__":
    print("Generating vocab...")
    gen_vocab("data/nus_sms_chinese.txt", "data/vocab/sms")

    print("Extracting sms data...")
    # need to get rid of the debug flag when extracting the real data
    data = extract_triples(
        build_parallel_paragraphs_from_txt('data/nus_sms_chinese.txt', debug = True), 
        min_paragraph_len=4)
    #gen_source_target_files(data, "sms_large")

    print("Done extracting...")
    
    # with open('data/sms_clean.data', 'wb') as outfile:
        # pickle.dump(data, outfile, pickle.HIGHEST_PROTOCOL)
    # with open('data/sms_clean.sample', 'w') as outfile:
    #     sample = json.dumps(data[:100], indent=4, sort_keys=True)
    #     outfile.write(sample)

    # print("Extracting lcmc data...")
    # data = extract_triples(build_parallel_paragraphs_lcmc())
    # with open('data/lcmc_clean.data', 'wb') as outfile:
    #     pickle.dump(data, outfile, pickle.HIGHEST_PROTOCOL)
    # with open('data/lcmc_clean.sample', 'w') as outfile:
    #     sample = json.dumps(data[:100], indent=4, sort_keys=True)
    #     outfile.write(sample)

    # print("Extracting weibo data...")

    # data = extract_triples(build_parallel_paragraphs_from_txt('data/weibo.txt'), min_paragraph_len=4, first_n=1000000)
    # with open('data/weibo_clean.data', 'wb') as outfile:
    #     pickle.dump(data, outfile, pickle.HIGHEST_PROTOCOL)
    # with open('data/weibo_clean.sample', 'w') as outfile:
    #     sample = json.dumps(data[:100], indent=4, sort_keys=True)
    #     outfile.write(sample)