#!/usr/bin/env python3

from aws_cdk import core

from hands_on_for_beginners_scalable_cdk.hands_on_for_beginners_scalable_cdk_stack import HandsOnForBeginnersScalableCdkStack


app = core.App()
env_EU = core.Environment(region="eu-west-1")
HandsOnForBeginnersScalableCdkStack(app, "hands-on-for-beginners-scalable-cdk", env=env_EU)

app.synth()
