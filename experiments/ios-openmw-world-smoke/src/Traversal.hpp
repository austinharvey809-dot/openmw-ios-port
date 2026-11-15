#pragma once
#include <experiments/ios-openmw-interior-smoke/src/Navigation.hpp>
#include <experiments/ios-openmw-exterior-smoke/src/Physics.hpp>
#include <memory>

namespace G4 {
class Traversal : public G2::Navigation {
    std::shared_ptr<G3::Physics> physics;
    double previous=-1;
public:
    void attach(std::shared_ptr<G3::Physics> value,osg::Vec3d entry,double angle){
        physics=std::move(value);start(entry,angle);physics->start(entry-osg::Vec3d(0,0,88));suspend();
    }
    void suspend(){G2::Navigation::suspend();previous=-1;}
    void jump(){if(physics)physics->jump();}
    void update(double now,bool loading=false){
        if(!physics || !std::isfinite(now))return;
        const double elapsed=previous<0?0:std::max(now-previous,0.);previous=now;
        const double dt=std::min(elapsed,G3::Physics::MaxFrameDelta);
        auto axis=[](float x){return std::isfinite(x)&&std::abs(x)>.15f?std::clamp(x,-1.f,1.f):0.f;};
        turn(-axis(lookX)*dt*1.8,axis(lookY)*dt*1.8);
        // Keep rendering while a detached replacement area is prepared. Freeze
        // translation/physics until commit so the player cannot cross its halo.
        if(loading)return;
        osg::Vec3d motion(std::cos(yaw)*axis(strafe)-std::sin(yaw)*axis(forward),
            std::sin(yaw)*axis(strafe)+std::cos(yaw)*axis(forward),0);
        if(motion.length2()>1)motion.normalize();eye=physics->move(motion*180,elapsed);
    }
};
}
