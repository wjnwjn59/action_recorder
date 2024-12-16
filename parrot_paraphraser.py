from parrot import Parrot
import torch
import warnings
warnings.filterwarnings("ignore")


def random_state(seed):
  torch.manual_seed(seed)
  if torch.cuda.is_available():
    torch.cuda.manual_seed_all(seed)

random_state(1234)

#Init models (make sure you init ONLY once if you integrate this to your code)
parrot = Parrot(model_tag="prithivida/parrot_paraphraser_on_T5")

phrases = ["Access to github website",
]

for phrase in phrases:
  print("-"*100)
  print("Input_phrase: ", phrase)
  print("-"*100)
  try:
      para_phrases = parrot.augment(input_phrase=phrase,
                               use_gpu=True,
                               do_diverse=True,             # Enable this to get more diverse paraphrases
                               adequacy_threshold = 0.80,   # Lower this numbers if no paraphrases returned
                               fluency_threshold = 0.80)
      for para_phrase in para_phrases:
          print(para_phrase)
  except:
      print("No paraphrases returned")
