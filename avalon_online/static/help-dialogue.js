/*
    Copyright 2023 by Simon Stepputtis, Carnegie Mellon University
    All rights reserved.
    This file is part of the Avalon-NLU repository,
    and is released under the "MIT License Agreement". Please see the LICENSE
    file that should have been included as part of this package.
*/

$(document).ready(function() {
    document.getElementById("help_button").addEventListener("click", function() {
        var box = document.getElementById("help-box");
        if (box.style.display === "none") {
            box.style.display = "block";
        } else {
            box.style.display = "none";
        }
    });
});

$(window).click(function(event) {
    var target = event.target;
    if (target.id != "help_button") {
        var box = document.getElementById("help-box");
        if (box.style.display === "block") {
            box.style.display = "none";
        }
    }
});