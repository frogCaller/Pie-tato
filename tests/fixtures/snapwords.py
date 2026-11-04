import os, sys
sys.path.insert(0, os.path.join(os.environ.get("PITATO_ROOT", ""), "tests"))
import pietato_all as g
yes = ["take a picture", "Take a photo please", "can you snap a pic", "send me a picture", "take a selfie",
       "snap a quick pic of the garage", "could you take another photo of the porch for me?", "send us a photo",
       "Selfie!", "picture please", "say cheese", "take a close-up picture of the cat",
       "can you take one more photo", "take a second picture", "take some photos of the yard", "grab a pic of the porch",
       "get me a picture of the front door", "snap a shot of the porch", "grab a snapshot of the porch",
       "why don't you take a picture of the porch?", "Why don’t you take a picture?", "photograph the porch",
       "take a couple of pictures", "take a quick snap of the garden", "take two photos", "take 3 pictures",
       "take a clearer picture please", "take a pic for me", "take a photo again", "snap some pics",
       "Take a picture with the garage camera", "I don't know, just take a picture", "if you don't mind take a picture",
       "take my picture", "hey bot, take a picture!", "please take a photo of the living room", "can you take pictures?",
       "take a picture, I didn't get one last time", "could you get us a photo of the driveway"]
no = ["what is in this picture", "I took a picture yesterday", "nice photo", "show me what you see", "take a look",
      "I get the picture", "did you get the photo I sent?", "I'll send you a picture later",
      "can you show me a picture of a cat?", "take a look at this picture", "I need to get a flu shot",
      "did you take my picture down?", "send the photos to grandma", "take a shot of tequila",
      "I took a selfie yesterday", "please don't take my picture", "no, never take my photo",
      "why did you take that picture?", "did you take a picture?", "where did you take this photo?",
      "I don't want you to take pictures of me", "I didn't ask you to take a picture", "do you take pictures?",
      "Please don’t take a photo", "when you take a selfie, smile", "grab a shot of tequila", "stop, don't take pictures",
      "take one of the pictures off the wall", "you shouldn't take photos of people", "does it take pictures?"]
again_yes = ["take another one", "another one please", "one more", "ok, one more!", "try again", "again", "Take another",
             "great, take another one!", "do it again", "snap another one"]
again_no = ["another one bites the dust", "one more thing", "say it again louder", "again and again and again it rains"]
bad = [t for t in yes if not g.friend_wants_photo(t)] + [t for t in no if g.friend_wants_photo(t)] \
    + [t for t in again_yes if not g.FRIEND_SNAP_AGAIN.search(t)] + [t for t in again_no if g.FRIEND_SNAP_AGAIN.search(t)]
print("wrong:", bad)
