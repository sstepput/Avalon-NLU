# Avalon NLU Testbed and Dataset

This repository accompanies our EMNLP 2023 Findings paper _"Long-Horizon Dialogue Understanding for Role Identification in the Game of Avalon with Large Language Models"_. Please also take a look at our project website: https://sstepput.github.io/Avalon-NLU/, which is having an interactive demo of our dataset. 

If you find this dataset or online version of Avalon useful, please cite our work:

```
@inproceedings{stepputtis2023longhorizon,
    title={Long-Horizon Dialogue Understanding for Role Identification in the Game of Avalon with Large Language Models},
    author={Stepputtis, Simon and Campbell, Joseph and Xie, Yaqi and Qi, Zhengyang and Zhang, Wenxin Sharon and Wang, Ruiyi and Rangreji, Sanketh and Lewis, Charles Michael and Sycara, Katia},
    booktitle={The 2023 Conference on Empirical Methods in Natural Language Processing},
    year={2023},
    url={https://openreview.net/forum?id=JKmsjKJ0Q8}
}
```

## Utilizing the Dataset
We provide the dataset of 20 games in the _/dataset_ folder, where each game is prepared as standard JSON files and can be read through TinyDB, or manual JSON parsing. You can explore the one such game through our interactive demo on our project website over here: https://sstepput.github.io/Avalon-NLU/. Each game is played with six players, having the roles of Merlin, Percival, Morgana, Assassin and to Servants. We provide the following information for each game:
- Game State 
    - Proposed parties
    - Previous parties
    - Party votes
    - Quest votes
    - Quest success and failures
    - Ground-Truth player roles
- Game Chat:
    - Each utterance has a persuasion strategy label
    - Each lie has a respective deception strategy label
- Player Beliefs:
    - Players have occasionally indicated their beliefs over other player's roles

## Running the Online version of Avalon
The online simulator will be released soon! 

## Changelog
- [November 2023] Initial release of the dataset and project website